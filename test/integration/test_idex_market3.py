#!/usr/bin/env python
from os.path import join, realpath
import sys;

from hummingbot.logger import HummingbotLogger

sys.path.insert(0, realpath(join(__file__, "../../../")))

import asyncio
import contextlib
from decimal import Decimal
import logging
import os
import time
import conf
from typing import (
    List,
    Optional
)
import unittest
import math
from hummingbot.core.clock import (
    Clock,
    ClockMode
)
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    BuyOrderCreatedEvent,
    MarketOrderFailureEvent,
    MarketEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderType,
    SellOrderCompletedEvent,
    SellOrderCreatedEvent,
    TradeFee,
    TradeType,
)
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)
from hummingbot.logger.struct_logger import METRICS_LOG_LEVEL
from hummingbot.connector.exchange.idex.idex_exchange import IdexExchange
from hummingbot.connector.exchange.idex.idex_utils import HBOT_BROKER_ID
from hummingbot.connector.markets_recorder import MarketsRecorder
from hummingbot.model.market_state import MarketState
from hummingbot.model.order import Order
from hummingbot.model.sql_connection_manager import (
    SQLConnectionManager,
    SQLConnectionType
)
from hummingbot.model.trade_fill import TradeFill
from hummingbot.client.config.fee_overrides_config_map import fee_overrides_config_map
from test.integration.humming_web_app import HummingWebApp
from test.integration.assets.mock_data.fixture_idex import FixtureIdex
from test.integration.humming_ws_server import HummingWsServerFactory
from unittest import mock

logging.basicConfig(level=METRICS_LOG_LEVEL)
# API_SECRET length must be multiple of 4 otherwise base64.b64decode will fail
API_MOCK_ENABLED = conf.mock_api_enabled is not None and conf.mock_api_enabled.lower() in ['true', 'yes', '1']
IDEX_API_KEY = "889fe7dd-ea60-4bf4-86f8-4eec39146510"
IDEX_SECRET_KEY = "tkDey53dr1ZlyM2tzUAu82l+nhgzxCJl"
IDEX_PRIVATE_KEY = "0227070369c04f55c66988ee3b272f8ae297cf7967ca7bad6d2f71f72072e18d"
API_BASE_URL = "https://api-eth.idex.io/"
WS_BASE_URL = "wss://websocket-eth.idex.io/v1/"

logging.basicConfig(level=logging.DEBUG)


class IdexExchangeUnitTest(unittest.TestCase):
    events: List[MarketEvent] = [
        MarketEvent.BuyOrderCompleted,
        MarketEvent.SellOrderCompleted,
        MarketEvent.OrderFilled,
        MarketEvent.TransactionFailure,
        MarketEvent.BuyOrderCreated,
        MarketEvent.SellOrderCreated,
        MarketEvent.OrderCancelled,
        MarketEvent.OrderFailure
    ]

    _test_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._test_logger is None:
            cls._test_logger = logging.getLogger(__name__)
        return cls._test_logger

    market: IdexExchange
    market_logger: EventLogger
    stack: contextlib.ExitStack
    trading_pair = "DIL-ETH"
    base_token, quote_token = trading_pair.split("-")

    @classmethod
    def setUpClass(cls):
        cls.ev_loop = asyncio.get_event_loop()
        if API_MOCK_ENABLED:
            cls.web_app = HummingWebApp.get_instance()
            cls.web_app.add_host_to_mock(API_BASE_URL, [])
            cls.web_app.start()
            cls.ev_loop.run_until_complete(cls.web_app.wait_til_started())
            cls._patcher = mock.patch("aiohttp.client.URL")
            cls._url_mock = cls._patcher.start()
            cls._url_mock.side_effect = cls.web_app.reroute_local
            cls.web_app.update_response("get", API_BASE_URL, "/v1/balances", FixtureIdex.BALANCES)
            cls.web_app.update_response("get", API_BASE_URL, "/v1/exchange", FixtureIdex.TRADE_FEES)
            cls.web_app.update_response("get", API_BASE_URL, "/v1/orders", FixtureIdex.ORDERS_STATUS)
            cls.web_app.update_response("delete", API_BASE_URL, "/v1/orders", FixtureIdex.CANCEL)

            HummingWsServerFactory.start_new_server(WS_BASE_URL)
            cls._ws_patcher = unittest.mock.patch("websockets.connect", autospec=True)
            cls._ws_mock = cls._ws_patcher.start()
            cls._ws_mock.side_effect = HummingWsServerFactory.reroute_ws_connect

            cls._t_nonce_patcher = unittest.mock.patch("hummingbot.core.utils.tracking_nonce.get_tracking_nonce")
            cls._t_nonce_mock = cls._t_nonce_patcher.start()
        cls.clock: Clock = Clock(ClockMode.REALTIME)
        cls.market: IdexExchange = IdexExchange(
            idex_api_key=IDEX_API_KEY,
            idex_api_secret_key=IDEX_SECRET_KEY,
            idex_wallet_private_key=IDEX_PRIVATE_KEY,
            trading_pairs=[cls.trading_pair]
        )
        print("Initializing Idex market... this will take about a minute.")
        cls.clock.add_iterator(cls.market)
        cls.stack: contextlib.ExitStack = contextlib.ExitStack()
        cls._clock = cls.stack.enter_context(cls.clock)
        cls.ev_loop.run_until_complete(cls.wait_til_ready())
        print("Ready.")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.stack.close()
        if API_MOCK_ENABLED:
            cls.web_app.stop()
            cls._patcher.stop()
            cls._t_nonce_patcher.stop()

    @classmethod
    async def wait_til_ready(cls, market=None):
        if market is None:
            market= cls.market
        while True:
            now = time.time()
            next_iteration = now // 1.0 + 1
            if market.ready:
                break
            else:
                await cls._clock.run_til(next_iteration)
            await asyncio.sleep(1.0)

    def setUp(self):
        self.db_path: str = realpath(join(__file__, "../idex_test.sqlite"))
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

        self.market_logger = EventLogger()
        for event_tag in self.events:
            self.market.add_listener(event_tag, self.market_logger)

    def tearDown(self):
        for event_tag in self.events:
            self.market.remove_listener(event_tag, self.market_logger)
        self.market_logger = None

    async def run_parallel_async(self, *tasks):
        future: asyncio.Future = safe_ensure_future(safe_gather(*tasks))
        while not future.done():
            now = time.time()
            next_iteration = now // 1.0 + 1
            await self._clock.run_til(next_iteration)
            await asyncio.sleep(1.0)
        return future.result()

    def run_parallel(self, *tasks):
        return self.ev_loop.run_until_complete(self.run_parallel_async(*tasks))

    '''
    def test_get_fee(self):
        limit_fee: TradeFee = self.market.get_fee("ETH", "USDC", OrderType.LIMIT_MAKER, TradeType.BUY, 1, 1)
        self.assertGreater(limit_fee.percent, 0)
        self.assertEqual(len(limit_fee.flat_fees), 0)
        market_fee: TradeFee = self.market.get_fee("ETH", "USDC", OrderType.LIMIT, TradeType.BUY, 1)
        self.assertGreater(market_fee.percent, 0)
        self.assertEqual(len(market_fee.flat_fees), 0)

    def test_fee_overrides_config(self):
        fee_overrides_config_map["coinbase_pro_taker_fee"].value = None
        taker_fee: TradeFee = self.market.get_fee("LINK", "ETH", OrderType.LIMIT, TradeType.BUY, Decimal(1),
                                                  Decimal('0.1'))
        self.assertAlmostEqual(Decimal("0.005"), taker_fee.percent)
        fee_overrides_config_map["coinbase_pro_taker_fee"].value = Decimal('0.2')
        taker_fee: TradeFee = self.market.get_fee("LINK", "ETH", OrderType.LIMIT, TradeType.BUY, Decimal(1),
                                                  Decimal('0.1'))
        self.assertAlmostEqual(Decimal("0.002"), taker_fee.percent)
        fee_overrides_config_map["coinbase_pro_maker_fee"].value = None
        maker_fee: TradeFee = self.market.get_fee("LINK", "ETH", OrderType.LIMIT_MAKER, TradeType.BUY, Decimal(1),
                                                  Decimal('0.1'))
        self.assertAlmostEqual(Decimal("0.005"), maker_fee.percent)
        fee_overrides_config_map["coinbase_pro_maker_fee"].value = Decimal('0.75')
        maker_fee: TradeFee = self.market.get_fee("LINK", "ETH", OrderType.LIMIT_MAKER, TradeType.BUY, Decimal(1),
                                                  Decimal('0.1'))
        self.assertAlmostEqual(Decimal("0.0075"), maker_fee.percent)
    '''

    def _place_order(self, is_buy, trading_pair, amount, order_type, price, nonce, fixture_resp, fixture_ws):
        order_id, exchange_order_id = None, None
        if API_MOCK_ENABLED:
            self._t_nonce_mock.return_value = nonce
            side = 'buy' if is_buy else 'sell'
            resp = fixture_resp.copy()
            exchange_order_id = resp["id"]
            resp["side"] = side
            self.web_app.update_response("post", API_BASE_URL, "v1/orders", resp)
        if is_buy:
            order_id = self.market.buy(trading_pair, amount, order_type, price)
        else:
            order_id = self.market.sell(trading_pair, amount, order_type, price)
        if API_MOCK_ENABLED:
            resp = fixture_ws.copy()
            resp["order_id"] = exchange_order_id
            resp["side"] = side
            HummingWsServerFactory.send_json_threadsafe(WS_BASE_URL, resp, delay=0.1)
        return order_id, exchange_order_id

    def _cancel_order(self, trading_pair, order_id, exchange_order_id, fixture_ws):
        if API_MOCK_ENABLED:
            self.web_app.update_response("delete", API_BASE_URL, f"v1/orders/{exchange_order_id}", exchange_order_id)
        self.market.cancel(trading_pair, order_id)
        if API_MOCK_ENABLED:
            resp = fixture_ws.copy()
            resp["orderId"] = exchange_order_id
            HummingWsServerFactory.send_json_threadsafe(WS_BASE_URL, resp, delay=0.1)

    '''
    def test_limit_taker_buy(self):
        self.assertGreater(self.market.get_balance("ETH"), Decimal("0.05"))
        trading_pair = "DIL-ETH"
        price: Decimal = self.market.get_price(trading_pair, True)
        amount: Decimal = Decimal("1.5")
        quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)
        order_id, _ = self._place_order(True, trading_pair, amount, OrderType.LIMIT, price, 10001,
                                        FixtureIdex.BUY_MARKET_ORDER, FixtureIdex.WS_AFTER_MARKET_BUY_2)
        [order_completed_event] = self.run_parallel(self.market_logger.wait_for(BuyOrderCompletedEvent))
        order_completed_event: BuyOrderCompletedEvent = order_completed_event
        trade_events: List[OrderFilledEvent] = [t for t in self.market_logger.event_log
                                                if isinstance(t, OrderFilledEvent)]
        base_amount_traded: Decimal = sum(t.amount for t in trade_events)
        quote_amount_traded: Decimal = sum(t.amount * t.price for t in trade_events)

        self.assertTrue([evt.order_type == OrderType.LIMIT_MAKER for evt in trade_events])
        self.assertEqual(order_id, order_completed_event.order_id)
        self.assertAlmostEqual(quantized_amount, order_completed_event.base_asset_amount)
        self.assertEqual("DIL", order_completed_event.base_asset)
        self.assertEqual("ETH", order_completed_event.quote_asset)
        self.assertAlmostEqual(base_amount_traded, order_completed_event.base_asset_amount)
        self.assertAlmostEqual(quote_amount_traded, order_completed_event.quote_asset_amount)
        self.assertTrue(any([isinstance(event, BuyOrderCreatedEvent) and event.order_id == order_id
                             for event in self.market_logger.event_log]))
        # Reset the logs
        self.market_logger.clear()    

    def test_limit_taker_sell(self):
        trading_pair = "DIL-ETH"
        price: Decimal = self.market.get_price(trading_pair, False)
        amount: Decimal = Decimal("1.5")
        quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)

        order_id, _ = self._place_order(False, trading_pair, quantized_amount, OrderType.LIMIT, price, 10001,
                                        FixtureIdex.BUY_MARKET_ORDER, FixtureIdex.WS_AFTER_MARKET_BUY_2)
        [order_completed_event] = self.run_parallel(self.market_logger.wait_for(SellOrderCompletedEvent))
        order_completed_event: SellOrderCompletedEvent = order_completed_event
        trade_events = [t for t in self.market_logger.event_log if isinstance(t, OrderFilledEvent)]
        base_amount_traded = sum(t.amount for t in trade_events)
        quote_amount_traded = sum(t.amount * t.price for t in trade_events)

        self.assertTrue([evt.order_type == OrderType.LIMIT_MAKER for evt in trade_events])
        self.assertEqual(order_id, order_completed_event.order_id)
        self.assertAlmostEqual(quantized_amount, order_completed_event.base_asset_amount)
        self.assertEqual("DIL", order_completed_event.base_asset)
        self.assertEqual("ETH", order_completed_event.quote_asset)
        self.assertAlmostEqual(base_amount_traded, order_completed_event.base_asset_amount)
        self.assertAlmostEqual(quote_amount_traded, order_completed_event.quote_asset_amount)
        self.assertTrue(any([isinstance(event, SellOrderCreatedEvent) and event.order_id == order_id
                             for event in self.market_logger.event_log]))
        # Reset the logs
        self.market_logger.clear()
    

    def test_cancel_order(self):
        trading_pair = "DIL-ETH"

        current_bid_price: Decimal = self.market.get_price(trading_pair, True)
        amount: Decimal = Decimal("5.0")
        self.assertGreater(self.market.get_balance("DIL"), amount)

        bid_price: Decimal = current_bid_price - Decimal("0.1") * current_bid_price
        quantize_bid_price: Decimal = self.market.quantize_order_price(trading_pair, bid_price)
        quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)
        order_id, exchange_order_id = self._place_order(True, trading_pair, quantized_amount, OrderType.LIMIT_MAKER,
                                                        quantize_bid_price, 10001, FixtureIdex.OPEN_BUY_LIMIT_ORDER,
                                                        FixtureIdex.WS_ORDER_OPEN)

        self._cancel_order(trading_pair, order_id, exchange_order_id, FixtureIdex.WS_ORDER_CANCELLED)
        [order_cancelled_event] = self.run_parallel(self.market_logger.wait_for(OrderCancelledEvent))
        order_cancelled_event: OrderCancelledEvent = order_cancelled_event
        self.assertEqual(order_cancelled_event.order_id, order_id)


    def test_cancel_all(self):
        trading_pair = "DIL-ETH"
        bid_price: Decimal = self.market.get_price(trading_pair, True) * Decimal("0.5")
        ask_price: Decimal = self.market.get_price(trading_pair, False) * 2
        amount: Decimal = 1 / bid_price
        quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)

        # Intentionally setting invalid price to prevent getting filled
        quantize_bid_price: Decimal = self.market.quantize_order_price(trading_pair, bid_price * Decimal("0.7"))
        quantize_ask_price: Decimal = self.market.quantize_order_price(trading_pair, ask_price * Decimal("1.5"))

        _, exchange_order_id = self._place_order(True, trading_pair, quantized_amount, OrderType.LIMIT_MAKER,
                                                 quantize_bid_price, 10001, FixtureIdex.OPEN_BUY_LIMIT_ORDER,
                                                 FixtureIdex.WS_ORDER_OPEN)
        _, exchange_order_id_2 = self._place_order(False, trading_pair, quantized_amount, OrderType.LIMIT_MAKER,
                                                   quantize_ask_price, 10002, FixtureIdex.OPEN_SELL_LIMIT_ORDER,
                                                   FixtureIdex.WS_ORDER_OPEN)
        #self.run_parallel(asyncio.sleep(1))

        if API_MOCK_ENABLED:
            self.web_app.update_response("delete", API_BASE_URL, f"/orders/{exchange_order_id}", exchange_order_id)
            self.web_app.update_response("delete", API_BASE_URL, f"/orders/{exchange_order_id_2}", exchange_order_id_2)
        [cancellation_results] = self.run_parallel(self.market.cancel_all(5))
        if API_MOCK_ENABLED:
            resp = FixtureIdex.WS_ORDER_CANCELLED.copy()
            resp["orderId"] = exchange_order_id
            HummingWsServerFactory.send_json_threadsafe(WS_BASE_URL, resp, delay=0.1)
            resp = FixtureIdex.WS_ORDER_CANCELLED.copy()
            resp["orderId"] = exchange_order_id_2
            HummingWsServerFactory.send_json_threadsafe(WS_BASE_URL, resp, delay=0.11)
        for cr in cancellation_results:
            self.logger().info(f"Cancellation Result: {cr.success}")
            self.assertEqual(cr.success, True)


    @unittest.skipUnless(any("test_list_orders" in arg for arg in sys.argv), "List order test requires manual action.")
    def test_list_orders(self):
        self.assertGreater(self.market.get_balance("DIL"), Decimal("0.1"))
        trading_pair = "DIL-ETH"
        amount: Decimal = Decimal("0.02")
        quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)

        current_bid_price: Decimal = self.market.get_price(trading_pair, True)
        bid_price: Decimal = current_bid_price + Decimal("0.05") * current_bid_price
        quantize_bid_price: Decimal = self.market.quantize_order_price(trading_pair, bid_price)

        self.market.buy(trading_pair, quantized_amount, OrderType.LIMIT_MAKER, quantize_bid_price)
        self.run_parallel(asyncio.sleep(1))
        [order_details] = self.run_parallel(self.market.list_orders())
        self.assertGreaterEqual(len(order_details), 1)

        self.market_logger.clear()

    def test_orders_saving_and_restoration(self):
        config_path: str = "test_config"
        strategy_name: str = "test_strategy"
        trading_pair: str = "DIL-ETH"
        sql: SQLConnectionManager = SQLConnectionManager(SQLConnectionType.TRADE_FILLS, db_path=self.db_path)
        order_id: Optional[str] = None
        recorder: MarketsRecorder = MarketsRecorder(sql, [self.market], config_path, strategy_name)
        recorder.start()

        try:
            self.assertEqual(0, len(self.market.tracking_states))

            # Try to put limit buy order for 0.04 ETH, and watch for order creation event.
            current_bid_price: Decimal = self.market.get_price(trading_pair, True)
            bid_price: Decimal = current_bid_price * Decimal("0.8")
            quantize_bid_price: Decimal = self.market.quantize_order_price(trading_pair, bid_price)

            amount: Decimal = Decimal("5.0")
            quantized_amount: Decimal = self.market.quantize_order_amount(trading_pair, amount)

            order_id, exchange_order_id = self._place_order(True, trading_pair, quantized_amount, OrderType.LIMIT_MAKER,
                                                            quantize_bid_price, 10001, FixtureIdex.OPEN_BUY_LIMIT_ORDER,
                                                            FixtureIdex.WS_ORDER_OPEN)
            [order_created_event] = self.run_parallel(self.market_logger.wait_for(BuyOrderCreatedEvent))
            order_created_event: BuyOrderCreatedEvent = order_created_event
            self.assertEqual(order_id, order_created_event.order_id)

            # Verify tracking states
            self.assertEqual(1, len(self.market.tracking_states))
            self.assertEqual(order_id, list(self.market.tracking_states.keys())[0])

            # Verify orders from recorder
            recorded_orders: List[Order] = recorder.get_orders_for_config_and_market(config_path, self.market)
            self.assertEqual(1, len(recorded_orders))
            self.assertEqual(order_id, recorded_orders[0].id)

            # Verify saved market states
            saved_market_states: MarketState = recorder.get_market_states(config_path, self.market)
            self.assertIsNotNone(saved_market_states)
            self.assertIsInstance(saved_market_states.saved_state, dict)
            self.assertGreater(len(saved_market_states.saved_state), 0)

            # Close out the current market and start another market.
            self.clock.remove_iterator(self.market)
            for event_tag in self.events:
                self.market.remove_listener(event_tag, self.market_logger)
            self.market: IdexExchange = IdexExchange(
                idex_api_key=IDEX_API_KEY,
                idex_api_secret_key=IDEX_SECRET_KEY,
                idex_wallet_private_key=IDEX_PRIVATE_KEY,
                trading_pairs=[trading_pair]
            )
            for event_tag in self.events:
                self.market.add_listener(event_tag, self.market_logger)
            recorder.stop()
            recorder = MarketsRecorder(sql, [self.market], config_path, strategy_name)
            recorder.start()
            saved_market_states = recorder.get_market_states(config_path, self.market)
            self.clock.add_iterator(self.market)
            self.assertEqual(0, len(self.market.limit_orders))
            self.assertEqual(0, len(self.market.tracking_states))
            self.market.restore_tracking_states(saved_market_states.saved_state)
            self.assertEqual(1, len(self.market.limit_orders))
            self.assertEqual(1, len(self.market.tracking_states))
            self.logger().info("About to start the cancel!")
            # Cancel the order and verify that the change is saved.
            self._cancel_order(trading_pair, order_id, exchange_order_id, FixtureIdex.WS_ORDER_CANCELLED)
            self.run_parallel(self.market_logger.wait_for(OrderCancelledEvent))
            order_id = None

            self.assertEqual(0, len(self.market.limit_orders))
            self.assertEqual(0, len(self.market.tracking_states))
            saved_market_states = recorder.get_market_states(config_path, self.market)
            self.assertEqual(0, len(saved_market_states.saved_state))
        finally:
            if order_id is not None:
                self._cancel_order(trading_pair, order_id, exchange_order_id, FixtureIdex.WS_ORDER_CANCELLED)
                self.run_parallel(self.market_logger.wait_for(OrderCancelledEvent))

            recorder.stop()
            os.unlink(self.db_path)

    def test_update_last_prices(self):
        # This is basic test to see if order_book last_trade_price is initiated and updated.
        for order_book in self.market.order_books.values():
            for _ in range(5):
                self.ev_loop.run_until_complete(asyncio.sleep(1))
                print(order_book.last_trade_price)
                self.assertFalse(math.isnan(order_book.last_trade_price))


    '''
    def test_order_fill_record(self):
        config_path: str = "test_config"
        strategy_name: str = "test_strategy"
        trading_pair: str = "DIL-ETH"
        sql: SQLConnectionManager = SQLConnectionManager(SQLConnectionType.TRADE_FILLS, db_path=self.db_path)
        order_id: Optional[str] = None
        recorder: MarketsRecorder = MarketsRecorder(sql, [self.market], config_path, strategy_name)
        recorder.start()

        try:
            # Try to buy 0.04 ETH from the exchange, and watch for completion event.
            price: Decimal = self.market.get_price(trading_pair, True)
            amount: Decimal = Decimal("1.5")
            order_id, exchange_order_id = self._place_order(True, trading_pair, amount, OrderType.LIMIT, price, 10001,
                                                            FixtureIdex.BUY_MARKET_ORDER,
                                                            FixtureIdex.WS_AFTER_MARKET_BUY_2)
            [buy_order_completed_event] = self.run_parallel(self.market_logger.wait_for(BuyOrderCompletedEvent))

            # Reset the logs
            self.market_logger.clear()

            # Try to sell back the same amount of ETH to the exchange, and watch for completion event.
            price: Decimal = self.market.get_price(trading_pair, False)
            amount = buy_order_completed_event.base_asset_amount
            order_id, exchange_order_id = self._place_order(False, trading_pair, amount, OrderType.LIMIT, price, 10002,
                                                            FixtureIdex.SELL_MARKET_ORDER,
                                                            FixtureIdex.WS_AFTER_MARKET_BUY_2)
            [sell_order_completed_event] = self.run_parallel(self.market_logger.wait_for(SellOrderCompletedEvent))

            # Query the persisted trade logs
            trade_fills: List[TradeFill] = recorder.get_trades_for_config(config_path)
            self.assertEqual(2, len(trade_fills))
            buy_fills: List[TradeFill] = [t for t in trade_fills if t.trade_type == "BUY"]
            sell_fills: List[TradeFill] = [t for t in trade_fills if t.trade_type == "SELL"]
            self.assertEqual(1, len(buy_fills))
            self.assertEqual(1, len(sell_fills))

            order_id = None

        finally:
            if order_id is not None:
                self._cancel_order(trading_pair, order_id, exchange_order_id, FixtureIdex.WS_ORDER_CANCELLED)
                self.run_parallel(self.market_logger.wait_for(OrderCancelledEvent))

            recorder.stop()
            os.unlink(self.db_path)


if __name__ == "__main__":
    logging.getLogger("hummingbot.core.event.event_reporter").setLevel(logging.WARNING)
    unittest.main()
