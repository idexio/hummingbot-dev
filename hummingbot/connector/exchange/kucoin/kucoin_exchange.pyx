import aiohttp
import asyncio
from decimal import Decimal
from libc.stdint cimport int64_t
import logging
import pandas as pd
from typing import (
    Any,
    Dict,
    List,
    AsyncIterable,
    Optional,
    Tuple
)
import json
import time

from hummingbot.core.clock cimport Clock
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book cimport OrderBook
from hummingbot.core.data_type.transaction_tracker import TransactionTracker
from hummingbot.core.event.events import (
    MarketEvent,
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    BuyOrderCreatedEvent,
    SellOrderCreatedEvent,
    MarketTransactionFailureEvent,
    MarketOrderFailureEvent,
    OrderType,
    TradeType,
    TradeFee
)
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_call_scheduler import AsyncCallScheduler
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)
from hummingbot.logger import HummingbotLogger
from hummingbot.connector.exchange.kucoin.kucoin_api_order_book_data_source import KucoinAPIOrderBookDataSource
from hummingbot.connector.exchange.kucoin.kucoin_auth import KucoinAuth
from hummingbot.connector.exchange.kucoin.kucoin_in_flight_order import KucoinInFlightOrder
from hummingbot.connector.exchange.kucoin.kucoin_order_book_tracker import KucoinOrderBookTracker
from hummingbot.connector.exchange.kucoin.kucoin_user_stream_tracker import KucoinUserStreamTracker
from hummingbot.connector.trading_rule cimport TradingRule
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce
from hummingbot.core.utils.estimate_fee import estimate_fee

km_logger = None
s_decimal_0 = Decimal(0)
s_decimal_NaN = Decimal("nan")
KUCOIN_ROOT_API = "https://api.kucoin.com"


class KucoinAPIError(IOError):
    def __init__(self, error_payload: Dict[str, Any]):
        super().__init__()
        self.error_payload = error_payload


cdef class KucoinExchangeTransactionTracker(TransactionTracker):
    cdef:
        KucoinExchange _owner

    def __init__(self, owner: KucoinExchange):
        super().__init__()
        self._owner = owner

    cdef c_did_timeout_tx(self, str tx_id):
        TransactionTracker.c_did_timeout_tx(self, tx_id)
        self._owner.c_did_timeout_tx(tx_id)

cdef class KucoinExchange(ExchangeBase):
    MARKET_BUY_ORDER_COMPLETED_EVENT_TAG = MarketEvent.BuyOrderCompleted.value
    MARKET_SELL_ORDER_COMPLETED_EVENT_TAG = MarketEvent.SellOrderCompleted.value
    MARKET_ORDER_CANCELLED_EVENT_TAG = MarketEvent.OrderCancelled.value
    MARKET_TRANSACTION_FAILURE_EVENT_TAG = MarketEvent.TransactionFailure.value
    MARKET_ORDER_FAILURE_EVENT_TAG = MarketEvent.OrderFailure.value
    MARKET_ORDER_FILLED_EVENT_TAG = MarketEvent.OrderFilled.value
    MARKET_BUY_ORDER_CREATED_EVENT_TAG = MarketEvent.BuyOrderCreated.value
    MARKET_SELL_ORDER_CREATED_EVENT_TAG = MarketEvent.SellOrderCreated.value
    API_CALL_TIMEOUT = 10.0
    UPDATE_ORDERS_INTERVAL = 10.0
    SHORT_POLL_INTERVAL = 5.0
    LONG_POLL_INTERVAL = 120.0

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global km_logger
        if km_logger is None:
            km_logger = logging.getLogger(__name__)
        return km_logger

    def __init__(self,
                 kucoin_api_key: str,
                 kucoin_passphrase: str,
                 kucoin_secret_key: str,
                 poll_interval: float = 5.0,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True):

        super().__init__()
        self._account_id = ""
        self._async_scheduler = AsyncCallScheduler(call_interval=0.5)
        self._ev_loop = asyncio.get_event_loop()
        self._kucoin_auth = KucoinAuth(api_key=kucoin_api_key, passphrase=kucoin_passphrase,
                                       secret_key=kucoin_secret_key)
        self._in_flight_orders = {}
        self._last_poll_timestamp = 0
        self._last_timestamp = 0
        self._order_book_tracker = KucoinOrderBookTracker(trading_pairs)
        self._poll_notifier = asyncio.Event()
        self._shared_client = None
        self._status_polling_task = None
        self._trading_required = trading_required
        self._trading_rules = {}
        self._trading_rules_polling_task = None
        self._tx_tracker = KucoinExchangeTransactionTracker(self)
        self._user_stream_tracker = KucoinUserStreamTracker(kucoin_auth=self._kucoin_auth)

    @staticmethod
    def split_trading_pair(trading_pair: str) -> Tuple[str, str]:
        try:
            m = trading_pair.split("-")
            return m[0], m[1]
        except Exception as e:
            raise ValueError(f"Error parsing trading_pair {trading_pair}: {str(e)}")

    @staticmethod
    def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> str:
        return exchange_trading_pair

    @staticmethod
    def convert_to_exchange_trading_pair(ku_trading_pair: str) -> str:
        return ku_trading_pair

    @property
    def name(self) -> str:
        return "kucoin"

    @property
    def order_book_tracker(self) -> KucoinOrderBookTracker:
        return self._order_book_tracker

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        return self._order_book_tracker.order_books

    @property
    def trading_rules(self) -> Dict[str, TradingRule]:
        return self._trading_rules

    @property
    def in_flight_orders(self) -> Dict[str, KucoinInFlightOrder]:
        return self._in_flight_orders

    @property
    def limit_orders(self) -> List[LimitOrder]:
        return [
            in_flight_order.to_limit_order()
            for in_flight_order in self._in_flight_orders.values()
        ]

    @property
    def tracking_states(self) -> Dict[str, Any]:
        return {
            key: value.to_json()
            for key, value in self._in_flight_orders.items()
        }

    def restore_tracking_states(self, saved_states: Dict[str, Any]):
        self._in_flight_orders.update({
            key: KucoinInFlightOrder.from_json(value)
            for key, value in saved_states.items()
        })

    @property
    def shared_client(self) -> str:
        return self._shared_client

    @shared_client.setter
    def shared_client(self, client: aiohttp.ClientSession):
        self._shared_client = client

    @property
    def user_stream_tracker(self) -> KucoinUserStreamTracker:
        return self._user_stream_tracker

    async def get_active_exchange_markets(self) -> pd.DataFrame:
        return await KucoinAPIOrderBookDataSource.get_active_exchange_markets()

    cdef c_start(self, Clock clock, double timestamp):
        self._tx_tracker.c_start(clock, timestamp)
        ExchangeBase.c_start(self, clock, timestamp)

    cdef c_stop(self, Clock clock):
        ExchangeBase.c_stop(self, clock)
        self._async_scheduler.stop()

    async def start_network(self):
        self._stop_network()
        self._order_book_tracker.start()
        self._trading_rules_polling_task = safe_ensure_future(self._trading_rules_polling_loop())
        if self._trading_required:
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            self._user_stream_tracker_task = safe_ensure_future(self._user_stream_tracker.start())
            self._user_stream_event_listener_task = safe_ensure_future(self._user_stream_event_listener())
            await self._update_balances()

    def _stop_network(self):
        self._order_book_tracker.stop()
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._trading_rules_polling_task is not None:
            self._trading_rules_polling_task.cancel()
            self._trading_rules_polling_task = None
        if self._user_stream_tracker_task is not None:
            self._user_stream_tracker_task.cancel()
            self._user_stream_tracker_task = None
        if self._user_stream_event_listener_task is not None:
            self._user_stream_event_listener_task.cancel()
            self._user_stream_event_listener_task = None

    async def stop_network(self):
        self._stop_network()

    async def check_network(self) -> NetworkStatus:
        try:
            await self._api_request(method="get", path_url="/api/v1/timestamp")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    cdef c_tick(self, double timestamp):
        cdef:
            double now = time.time()
            double poll_interval = (self.SHORT_POLL_INTERVAL
                                    if now - self.user_stream_tracker.last_recv_time > 60.0
                                    else self.LONG_POLL_INTERVAL)
            int64_t last_tick = <int64_t> (self._last_timestamp / poll_interval)
            int64_t current_tick = <int64_t> (timestamp / poll_interval)
        ExchangeBase.c_tick(self, timestamp)
        self._tx_tracker.c_tick(timestamp)
        if current_tick > last_tick:
            if not self._poll_notifier.is_set():
                self._poll_notifier.set()
        self._last_timestamp = timestamp

    async def _iter_user_event_queue(self) -> AsyncIterable[Dict[str, any]]:
        while True:
            try:
                yield await self._user_stream_tracker.user_stream.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unknown error. Retrying after 1 seconds.",
                    exc_info=True,
                    app_warning_msg="Could not fetch user events from Binance. Check API key and network connection."
                )
                await asyncio.sleep(1.0)

    async def _user_stream_event_listener(self):
        async for event_message in self._iter_user_event_queue():
            try:
                event_type = event_message.get("type")
                event_topic = event_message.get("topic")
                execution_data = event_message.get("data")

                # Refer to https://docs.kucoin.com/#private-order-change-events
                if event_type == "message" and event_topic == "/spotMarket/tradeOrders":
                    execution_status = execution_data["status"]
                    execution_type = execution_data["type"]
                    client_order_id = execution_data["clientOid"]

                    tracked_order = self._in_flight_orders.get(client_order_id)

                    if tracked_order is None:
                        self.logger().debug(f"Unrecognized order ID from user stream: {client_order_id}.")
                        self.logger().debug(f"Event: {event_message}")
                        continue
                elif event_type == "message" and event_topic == "/account/balance":
                    currency = execution_data["currency"]
                    available_balance = Decimal(execution_data["available"])
                    total_balance = Decimal(execution_data["total"])
                    self._account_balances.update({currency: total_balance})
                    self._account_available_balances.update({currency: available_balance})
                    continue
                else:
                    continue

                if (execution_status == "open" or execution_status == "match") and execution_type != "open":
                    if Decimal(execution_data["matchSize"]) > 0:
                        execute_amount_diff = Decimal(execution_data["matchSize"])
                        execute_price = Decimal(execution_data["price"])
                        tracked_order.executed_amount_base = Decimal(execution_data["filledSize"])
                        tracked_order.executed_amount_quote = Decimal(execution_data["filledSize"]) * Decimal(
                            execute_price)
                        self.logger().info(f"Filled {execute_amount_diff} out of {tracked_order.amount} of the "
                                           f"order {tracked_order.client_order_id}.")
                        self.c_trigger_event(self.MARKET_ORDER_FILLED_EVENT_TAG,
                                             OrderFilledEvent(
                                                 self._current_timestamp,
                                                 tracked_order.client_order_id,
                                                 tracked_order.trading_pair,
                                                 tracked_order.trade_type,
                                                 tracked_order.order_type,
                                                 execute_price,
                                                 execute_amount_diff,
                                                 self.c_get_fee(
                                                     tracked_order.base_asset,
                                                     tracked_order.quote_asset,
                                                     tracked_order.order_type,
                                                     tracked_order.trade_type,
                                                     execute_price,
                                                     execute_amount_diff,
                                                 ),
                                                 tracked_order.exchange_order_id
                                             ))
                if (execution_status == "done" or execution_status == "match") and (execution_type == "match" or execution_type == "filled"):
                    tracked_order.executed_amount_base = Decimal(execution_data["filledSize"])
                    tracked_order.executed_amount_quote = Decimal(execution_data["filledSize"]) * Decimal(
                        execution_data["price"])
                    if tracked_order.trade_type == TradeType.BUY:
                        self.logger().info(f"The market buy order {tracked_order.client_order_id} has completed "
                                           f"according to KuCoin user stream.")
                        self.c_trigger_event(self.MARKET_BUY_ORDER_COMPLETED_EVENT_TAG,
                                             BuyOrderCompletedEvent(self._current_timestamp,
                                                                    tracked_order.client_order_id,
                                                                    tracked_order.base_asset,
                                                                    tracked_order.quote_asset,
                                                                    (tracked_order.fee_asset
                                                                     or tracked_order.base_asset),
                                                                    tracked_order.executed_amount_base,
                                                                    tracked_order.executed_amount_quote,
                                                                    tracked_order.fee_paid,
                                                                    tracked_order.order_type,
                                                                    exchange_order_id=tracked_order.exchange_order_id))
                    else:
                        self.logger().info(f"The market sell order {tracked_order.client_order_id} has completed "
                                           f"according to KuCoin user stream.")
                        self.c_trigger_event(self.MARKET_SELL_ORDER_COMPLETED_EVENT_TAG,
                                             SellOrderCompletedEvent(self._current_timestamp,
                                                                     tracked_order.client_order_id,
                                                                     tracked_order.base_asset,
                                                                     tracked_order.quote_asset,
                                                                     (tracked_order.fee_asset
                                                                      or tracked_order.quote_asset),
                                                                     tracked_order.executed_amount_base,
                                                                     tracked_order.executed_amount_quote,
                                                                     tracked_order.fee_paid,
                                                                     tracked_order.order_type,
                                                                     exchange_order_id=tracked_order.exchange_order_id))
                    self.c_stop_tracking_order(tracked_order.client_order_id)
                elif execution_status == "done" and execution_type == "canceled":
                    self.logger().info(f"Successfully cancelled order {tracked_order.client_order_id}.")
                    self.c_trigger_event(self.MARKET_ORDER_CANCELLED_EVENT_TAG,
                                         OrderCancelledEvent(self._current_timestamp,
                                                             tracked_order.client_order_id,
                                                             exchange_order_id=tracked_order.exchange_order_id))
                    self.c_stop_tracking_order(tracked_order.client_order_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await asyncio.sleep(5.0)

    async def _http_client(self) -> aiohttp.ClientSession:
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client

    async def _api_request(self,
                           method,
                           path_url,
                           params: Optional[Dict[str, Any]] = None,
                           data=None,
                           is_auth_required: bool = False,
                           is_partner_required: bool = False) -> Dict[str, Any]:
        url = KUCOIN_ROOT_API + path_url
        client = await self._http_client()
        if is_auth_required:
            if is_partner_required:
                headers = self._kucoin_auth.add_auth_to_params(method, path_url, params, partner_header=True)
            else:
                headers = self._kucoin_auth.add_auth_to_params(method, path_url, params)
        else:
            headers = {"Content-Type": "application/json"}

        post_json = json.dumps(params)
        if method == "get":
            response = await client.get(url, headers=headers)
        elif method == "post":
            response = await client.post(url, data=post_json, headers=headers)
        elif method == "delete":
            response = await client.delete(url, headers=headers)
        else:
            response = False

        if response:
            if response.status != 200:
                raise IOError(f"Error fetching data from {url}. HTTP status is {response.status}.")
            try:
                parsed_response = json.loads(await response.text())
            except Exception:
                raise IOError(f"Error parsing data from {url}.")
            return parsed_response

    async def _update_balances(self):
        cdef:
            str path_url = "/api/v1/accounts?type=trade"
            str asset_name
            set local_asset_names = set(self._account_balances.keys())
            set remote_asset_names = set()

        data = await self._api_request("get", path_url=path_url, is_auth_required=True)
        if data:
            for balance_entry in data["data"]:
                asset_name = balance_entry["currency"]
                self._account_available_balances[asset_name] = Decimal(balance_entry["available"])
                self._account_balances[asset_name] = Decimal(balance_entry["balance"])
                remote_asset_names.add(asset_name)

            asset_names_to_remove = local_asset_names.difference(remote_asset_names)
            for asset_name in asset_names_to_remove:
                del self._account_available_balances[asset_name]
                del self._account_balances[asset_name]

    cdef object c_get_fee(self,
                          str base_currency,
                          str quote_currency,
                          object order_type,
                          object order_side,
                          object amount,
                          object price):
        # There is no API for checking user's fee tier
        # Fee info from https://www.kucoin.com/vip/fee
        """
        if order_type is OrderType.LIMIT and fee_overrides_config_map["kucoin_maker_fee"].value is not None:
            return TradeFee(percent=fee_overrides_config_map["kucoin_maker_fee"].value / Decimal("100"))
        if order_type is OrderType.MARKET and fee_overrides_config_map["kucoin_taker_fee"].value is not None:
            return TradeFee(percent=fee_overrides_config_map["kucoin_taker_fee"].value / Decimal("100"))
        return TradeFee(percent=Decimal("0.001"))
        """
        is_maker = order_type is OrderType.LIMIT_MAKER
        return estimate_fee("kucoin", is_maker)

    async def _update_trading_rules(self):
        cdef:
            # The poll interval for trade rules is 60 seconds.
            int64_t last_tick = <int64_t> (self._last_timestamp / 60.0)
            int64_t current_tick = <int64_t> (self._current_timestamp / 60.0)
        if current_tick > last_tick or len(self._trading_rules) < 1:
            exchange_info = await self._api_request("get", path_url="/api/v1/symbols")
            trading_rules_list = self._format_trading_rules(exchange_info)
            self._trading_rules.clear()
            for trading_rule in trading_rules_list:
                self._trading_rules[trading_rule.trading_pair] = trading_rule

    def _format_trading_rules(self, raw_trading_pair_info: List[Dict[str, Any]]) -> List[TradingRule]:
        cdef:
            list trading_rules = []

        for info in raw_trading_pair_info["data"]:
            try:
                trading_rules.append(
                    TradingRule(trading_pair=info["symbol"],
                                min_order_size=Decimal(info["baseMinSize"]),
                                max_order_size=Decimal(info["baseMaxSize"]),
                                min_price_increment=Decimal(info['priceIncrement']),
                                min_base_amount_increment=Decimal(info['baseIncrement']),
                                min_quote_amount_increment=Decimal(info['quoteIncrement']),
                                min_notional_size=Decimal(info["quoteMinSize"]))
                )
            except Exception:
                self.logger().error(f"Error parsing the trading_pair rule {info}. Skipping.", exc_info=True)
        return trading_rules

    async def get_order_status(self, exchange_order_id: str) -> Dict[str, Any]:
        path_url = f"/api/v1/orders/{exchange_order_id}"
        return await self._api_request("get", path_url=path_url, is_auth_required=True)

    async def _update_order_status(self):
        cdef:
            # The poll interval for order status is 10 seconds.
            int64_t last_tick = <int64_t> (self._last_poll_timestamp / self.UPDATE_ORDERS_INTERVAL)
            int64_t current_tick = <int64_t> (self._current_timestamp / self.UPDATE_ORDERS_INTERVAL)

        if current_tick > last_tick and len(self._in_flight_orders) > 0:
            tracked_orders = list(self._in_flight_orders.values())
            for tracked_order in tracked_orders:
                exchange_order_id = await tracked_order.get_exchange_order_id()
                order_update = await self.get_order_status(exchange_order_id)
                if order_update is None:
                    self.logger().network(
                        f"Error fetching status update for the order {tracked_order.client_order_id}: "
                        f"{order_update}.",
                        app_warning_msg=f"Could not fetch updates for the order {tracked_order.client_order_id}. "
                                        f"The order has either been filled or canceled."
                    )
                    continue

                order_state = order_update["data"]["isActive"]
                if order_state:
                    continue

                # Calculate the newly executed amount for this update.
                if order_update["data"]["opType"] == "DEAL":
                    if order_state:
                        tracked_order.last_state = "DEAL"
                    else:
                        tracked_order.last_state = "DONE"
                else:
                    tracked_order.last_state = "CANCEL"
                new_confirmed_amount = Decimal(
                    order_update["data"]["dealFunds"])  # API isn't detailed enough assuming dealSize
                execute_amount_diff = Decimal(order_update["data"]["dealSize"])

                if execute_amount_diff > s_decimal_0:
                    tracked_order.executed_amount_base = Decimal(order_update["data"]["dealSize"])
                    tracked_order.executed_amount_quote = new_confirmed_amount
                    tracked_order.fee_paid = Decimal(order_update["data"]["fee"])
                    execute_price = Decimal(order_update["data"]["dealFunds"]) / execute_amount_diff
                    order_filled_event = OrderFilledEvent(
                        self._current_timestamp,
                        tracked_order.client_order_id,
                        tracked_order.trading_pair,
                        tracked_order.trade_type,
                        tracked_order.order_type,
                        float(execute_price),
                        float(execute_amount_diff),
                        self.c_get_fee(
                            tracked_order.base_asset,
                            tracked_order.quote_asset,
                            tracked_order.order_type,
                            tracked_order.trade_type,
                            float(execute_price),
                            float(execute_amount_diff),
                        ),
                        exchange_trade_id=exchange_order_id,
                    )
                    self.logger().info(f"Filled {execute_amount_diff} out of {tracked_order.amount} of the "
                                       f"order {tracked_order.client_order_id}.")
                    self.c_trigger_event(self.MARKET_ORDER_FILLED_EVENT_TAG, order_filled_event)

                if order_state is False and order_update["data"]["cancelExist"] is False:
                    self.c_stop_tracking_order(tracked_order.client_order_id)
                    if tracked_order.trade_type is TradeType.BUY:
                        self.logger().info(f"The market buy order {tracked_order.client_order_id} has completed "
                                           f"according to order status API.")
                        self.c_trigger_event(self.MARKET_BUY_ORDER_COMPLETED_EVENT_TAG,
                                             BuyOrderCompletedEvent(self._current_timestamp,
                                                                    tracked_order.client_order_id,
                                                                    tracked_order.base_asset,
                                                                    tracked_order.quote_asset,
                                                                    tracked_order.fee_asset or tracked_order.base_asset,
                                                                    float(tracked_order.executed_amount_base),
                                                                    float(tracked_order.executed_amount_quote),
                                                                    float(tracked_order.fee_paid),
                                                                    tracked_order.order_type,
                                                                    exchange_order_id=tracked_order.exchange_order_id))
                    else:
                        self.logger().info(f"The market sell order {tracked_order.client_order_id} has completed "
                                           f"according to order status API.")
                        self.c_trigger_event(self.MARKET_SELL_ORDER_COMPLETED_EVENT_TAG,
                                             SellOrderCompletedEvent(self._current_timestamp,
                                                                     tracked_order.client_order_id,
                                                                     tracked_order.base_asset,
                                                                     tracked_order.quote_asset,
                                                                     tracked_order.fee_asset or tracked_order.quote_asset,
                                                                     float(tracked_order.executed_amount_base),
                                                                     float(tracked_order.executed_amount_quote),
                                                                     float(tracked_order.fee_paid),
                                                                     tracked_order.order_type,
                                                                     exchange_order_id=tracked_order.exchange_order_id))

                if order_state is False and order_update["data"]["cancelExist"] is True:
                    self.c_stop_tracking_order(tracked_order.client_order_id)
                    self.logger().info(f"The market order {tracked_order.client_order_id} has been cancelled according"
                                       f" to order status API.")
                    self.c_trigger_event(self.MARKET_ORDER_CANCELLED_EVENT_TAG,
                                         OrderCancelledEvent(self._current_timestamp,
                                                             tracked_order.client_order_id,
                                                             exchange_order_id=tracked_order.exchange_order_id))

    async def _status_polling_loop(self):
        while True:
            try:
                self._poll_notifier = asyncio.Event()
                await self._poll_notifier.wait()

                await safe_gather(
                    self._update_balances(),
                    self._update_order_status(),
                )
                self._last_poll_timestamp = self._current_timestamp
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network("Unexpected error while fetching account updates.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch account updates from Kucoin. "
                                                      "Check API key and network connection.")
                await asyncio.sleep(0.5)

    async def _trading_rules_polling_loop(self):
        while True:
            try:
                await self._update_trading_rules()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network("Unexpected error while fetching trading rules.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch new trading rules from Kucoin. "
                                                      "Check network connection.")
                await asyncio.sleep(0.5)

    @property
    def status_dict(self) -> Dict[str, bool]:
        return {
            "order_books_initialized": self._order_book_tracker.ready,
            "account_balance": self._account_balances if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0
        }

    @property
    def ready(self) -> bool:
        # print(self.status_dict)
        return all(self.status_dict.values())

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER]

    async def place_order(self,
                          order_id: str,
                          trading_pair: str,
                          amount: Decimal,
                          is_buy: bool,
                          order_type: OrderType,
                          price: Decimal) -> str:
        path_url = "/api/v1/orders"
        side = "buy" if is_buy else "sell"
        order_type_str = "limit"
        params = {
            "size": str(amount),
            "clientOid": order_id,
            "side": side,
            "symbol": trading_pair,
            "type": order_type_str,
        }
        if order_type is OrderType.LIMIT:
            params["price"] = str(price)
        elif order_type is OrderType.LIMIT_MAKER:
            params["price"] = str(price)
            params["postOnly"] = True
        exchange_order_id = await self._api_request(
            "post",
            path_url=path_url,
            params=params,
            data=params,
            is_auth_required=True,
            is_partner_required=True
        )
        return str(exchange_order_id["data"]["orderId"])

    async def execute_buy(self,
                          order_id: str,
                          trading_pair: str,
                          amount: Decimal,
                          order_type: OrderType,
                          price: Decimal):
        cdef:
            TradingRule trading_rule = self._trading_rules[trading_pair]
            double quote_amount
            object decimal_amount
            object decimal_price
            str exchange_order_id
            object tracked_order

        if order_type is OrderType.LIMIT or order_type is OrderType.LIMIT_MAKER:
            decimal_amount = self.c_quantize_order_amount(trading_pair, amount)
            decimal_price = self.c_quantize_order_price(trading_pair, price)
            if decimal_amount < trading_rule.min_order_size:
                raise ValueError(f"Buy order amount {decimal_amount} is lower than the minimum order size "
                                 f"{trading_rule.min_order_size}.")
        try:
            exchange_order_id = await self.place_order(order_id, trading_pair, decimal_amount, True, order_type,
                                                       decimal_price)
            self.c_start_tracking_order(
                client_order_id=order_id,
                exchange_order_id=exchange_order_id,
                trading_pair=trading_pair,
                order_type=order_type,
                trade_type=TradeType.BUY,
                price=decimal_price,
                amount=decimal_amount
            )
            tracked_order = self._in_flight_orders.get(order_id)
            if tracked_order is not None:
                self.logger().info(f"Created {order_type} buy order {order_id} for {decimal_amount} {trading_pair}.")
            self.c_trigger_event(self.MARKET_BUY_ORDER_CREATED_EVENT_TAG,
                                 BuyOrderCreatedEvent(
                                     self._current_timestamp,
                                     order_type,
                                     trading_pair,
                                     float(decimal_amount),
                                     float(decimal_price),
                                     order_id,
                                     exchange_order_id=tracked_order.exchange_order_id
                                 ))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.c_stop_tracking_order(order_id)
            order_type_str = order_type.name.lower()
            self.logger().network(
                f"Error submitting buy {order_type_str} order to Kucoin for "
                f"{decimal_amount} {trading_pair} "
                f"{decimal_price}.",
                exc_info=True,
                app_warning_msg=f"Failed to submit buy order to Kucoin. Check API key and network connection."
            )
            self.c_trigger_event(self.MARKET_ORDER_FAILURE_EVENT_TAG,
                                 MarketOrderFailureEvent(self._current_timestamp, order_id, order_type))

    cdef str c_buy(self,
                   str trading_pair,
                   object amount,
                   object order_type = OrderType.LIMIT,
                   object price = s_decimal_0,
                   dict kwargs = {}):
        cdef:
            int64_t tracking_nonce = <int64_t> get_tracking_nonce()
            str order_id = f"buy-{trading_pair}-{tracking_nonce}"

        safe_ensure_future(self.execute_buy(order_id, trading_pair, amount, order_type, price))
        return order_id

    async def execute_sell(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           order_type: OrderType,
                           price: Decimal):
        cdef:
            TradingRule trading_rule = self._trading_rules[trading_pair]
            object decimal_amount
            object decimal_price
            str exchange_order_id
            object tracked_order

        decimal_amount = self.quantize_order_amount(trading_pair, amount)
        decimal_price = self.c_quantize_order_price(trading_pair, price)
        if decimal_amount < trading_rule.min_order_size:
            raise ValueError(f"Sell order amount {decimal_amount} is lower than the minimum order size "
                             f"{trading_rule.min_order_size}.")

        try:
            exchange_order_id = await self.place_order(order_id, trading_pair, decimal_amount, False, order_type,
                                                       decimal_price)
            self.c_start_tracking_order(
                client_order_id=order_id,
                exchange_order_id=exchange_order_id,
                trading_pair=trading_pair,
                order_type=order_type,
                trade_type=TradeType.SELL,
                price=decimal_price,
                amount=decimal_amount
            )
            tracked_order = self._in_flight_orders.get(order_id)
            if tracked_order is not None:
                self.logger().info(f"Created {order_type} sell order {order_id} for {decimal_amount} {trading_pair}.")
            self.c_trigger_event(self.MARKET_SELL_ORDER_CREATED_EVENT_TAG,
                                 SellOrderCreatedEvent(
                                     self._current_timestamp,
                                     order_type,
                                     trading_pair,
                                     float(decimal_amount),
                                     float(decimal_price),
                                     order_id,
                                     exchange_order_id=exchange_order_id
                                 ))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.c_stop_tracking_order(order_id)
            order_type_str = order_type.name.lower()
            self.logger().network(
                f"Error submitting sell {order_type_str} order to Kucoin for "
                f"{decimal_amount} {trading_pair} "
                f"{decimal_price}.",
                exc_info=True,
                app_warning_msg=f"Failed to submit sell order to Kucoin. Check API key and network connection."
            )
            self.c_trigger_event(self.MARKET_ORDER_FAILURE_EVENT_TAG,
                                 MarketOrderFailureEvent(self._current_timestamp, order_id, order_type))

    cdef str c_sell(self,
                    str trading_pair,
                    object amount,
                    object order_type = OrderType.LIMIT,
                    object price = s_decimal_0,
                    dict kwargs = {}):
        cdef:
            int64_t tracking_nonce = <int64_t> get_tracking_nonce()
            str order_id = f"sell-{trading_pair}-{tracking_nonce}"
        safe_ensure_future(self.execute_sell(order_id, trading_pair, amount, order_type, price))
        return order_id

    async def execute_cancel(self, trading_pair: str, order_id: str):
        try:
            tracked_order = self._in_flight_orders.get(order_id)
            if tracked_order is None:
                raise ValueError(f"Failed to cancel order - {order_id}. Order not found.")
            path_url = f"/api/v1/orders/{tracked_order.exchange_order_id}"
            await self._api_request("delete", path_url=path_url, is_auth_required=True)
        except Exception as e:
            self.logger().network(
                f"Failed to cancel order {order_id}: {str(e)}",
                exc_info=True,
                app_warning_msg=f"Failed to cancel the order {order_id} on Kucoin. "
                                f"Check API key and network connection."
            )

    cdef c_cancel(self, str trading_pair, str order_id):
        safe_ensure_future(self.execute_cancel(trading_pair, order_id))
        return order_id

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        path_url = "/api/v1/orders"
        cancellation_results = []
        try:
            cancel_all_results = await self._api_request(
                "delete",
                path_url=path_url,
                is_auth_required=True
            )
            for oid in cancel_all_results["data"]["cancelledOrderIds"]:
                tracked_order = self._in_flight_orders.get(oid)
                cancellation_results.append(CancellationResult(oid, True))
                if tracked_order is not None:
                    self.c_trigger_event(self.MARKET_ORDER_CANCELLED_EVENT_TAG,
                                         OrderCancelledEvent(self._current_timestamp,
                                                             tracked_order.client_order_id,
                                                             exchange_order_id=tracked_order.exchange_order_id))
        except Exception as e:
            self.logger().network(
                f"Failed to cancel all orders.",
                exc_info=True,
                app_warning_msg=f"Failed to cancel all orders on Kucoin. Check API key and network connection."
            )
        return cancellation_results

    cdef OrderBook c_get_order_book(self, str trading_pair):
        cdef:
            dict order_books = self._order_book_tracker.order_books

        if trading_pair not in order_books:
            raise ValueError(f"No order book exists for '{trading_pair}'.")
        return order_books.get(trading_pair)

    cdef c_did_timeout_tx(self, str tracking_id):
        self.c_trigger_event(self.MARKET_TRANSACTION_FAILURE_EVENT_TAG,
                             MarketTransactionFailureEvent(self._current_timestamp, tracking_id))

    cdef c_start_tracking_order(self,
                                str client_order_id,
                                str exchange_order_id,
                                str trading_pair,
                                object order_type,
                                object trade_type,
                                object price,
                                object amount):
        self._in_flight_orders[client_order_id] = KucoinInFlightOrder(
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            order_type=order_type,
            trade_type=trade_type,
            price=price,
            amount=amount
        )

    cdef c_stop_tracking_order(self, str order_id):
        if order_id in self._in_flight_orders:
            del self._in_flight_orders[order_id]

    cdef object c_get_order_price_quantum(self, str trading_pair, object price):
        cdef:
            TradingRule trading_rule = self._trading_rules[trading_pair]
        return trading_rule.min_price_increment

    cdef object c_get_order_size_quantum(self, str trading_pair, object order_size):
        cdef:
            TradingRule trading_rule = self._trading_rules[trading_pair]
        return Decimal(trading_rule.min_base_amount_increment)

    cdef object c_quantize_order_amount(self, str trading_pair, object amount, object price=s_decimal_0):
        cdef:
            TradingRule trading_rule = self._trading_rules[trading_pair]
            object quantized_amount = ExchangeBase.c_quantize_order_amount(self, trading_pair, amount)
            object current_price = self.c_get_price(trading_pair, False)
            object notional_size

        # Check against min_order_size. If not passing check, return 0.
        if quantized_amount < trading_rule.min_order_size:
            return s_decimal_0

        # Check against max_order_size. If not passing check, return maximum.
        if quantized_amount > trading_rule.max_order_size:
            return trading_rule.max_order_size

        if price == s_decimal_0:
            notional_size = current_price * quantized_amount
        else:
            notional_size = price * quantized_amount
        # Add 1% as a safety factor in case the prices changed while making the order.
        if notional_size < trading_rule.min_notional_size * Decimal("1.01"):
            return s_decimal_0

        return quantized_amount

    def get_price(self, trading_pair: str, is_buy: bool) -> Decimal:
        return self.c_get_price(trading_pair, is_buy)

    def buy(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
            price: Decimal = s_decimal_NaN, **kwargs) -> str:
        return self.c_buy(trading_pair, amount, order_type, price, kwargs)

    def sell(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
             price: Decimal = s_decimal_NaN, **kwargs) -> str:
        return self.c_sell(trading_pair, amount, order_type, price, kwargs)

    def cancel(self, trading_pair: str, client_order_id: str):
        return self.c_cancel(trading_pair, client_order_id)

    def get_fee(self,
                base_currency: str,
                quote_currency: str,
                order_type: OrderType,
                order_side: TradeType,
                amount: Decimal,
                price: Decimal = s_decimal_NaN) -> TradeFee:
        return self.c_get_fee(base_currency, quote_currency, order_type, order_side, amount, price)

    def get_order_book(self, trading_pair: str) -> OrderBook:
        return self.c_get_order_book(trading_pair)
