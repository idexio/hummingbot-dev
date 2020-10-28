import asyncio
import pandas as pd

from dataclasses import asdict
from decimal import Decimal
from typing import Optional, List, Dict, Any

from async_timeout import timeout

from hummingbot.connector.exchange_base import ExchangeBase, s_decimal_NaN
from hummingbot.connector.in_flight_order_base import InFlightOrderBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.event.events import OrderType, TradeType, TradeFee
from hummingbot.core.network_base import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.core.utils.estimate_fee import estimate_fee

from .client.asyncio import AsyncIdexClient
from .idex_auth import IdexAuth
from .idex_in_flight_order import IdexInFlightOrder
from .idex_order_book_tracker import IdexOrderBookTracker
from .idex_user_stream_tracker import IdexUserStreamTracker
from .types.rest.request import RestRequestCancelOrder, RestRequestOrder, OrderSide
from .utils import to_idex_pair, to_idex_order_type, create_id, EXCHANGE_NAME


class IdexExchange(ExchangeBase):

    name: str = EXCHANGE_NAME

    def __init__(self,
                 idex_api_key: str,
                 idex_api_secret_key: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True):
        """
        :param idex_com_api_key: The API key to connect to private idex.io APIs.
        :param idex_com_secret_key: The API secret.
        :param trading_pairs: The market trading pairs which to track order book data.
        :param trading_required: Whether actual trading is needed.
        """
        super().__init__()
        self._trading_required = trading_required
        self._idex_auth: IdexAuth = IdexAuth(idex_api_key, idex_api_secret_key)
        self._client: AsyncIdexClient = AsyncIdexClient(auth=self._idex_auth)
        self._order_book_tracker = IdexOrderBookTracker(trading_pairs=trading_pairs)
        self._user_stream_tracker = IdexUserStreamTracker(self._idex_com_auth, trading_pairs)
        self._ev_loop = asyncio.get_event_loop()
        self._shared_client = None
        self._poll_notifier = asyncio.Event()
        self._last_timestamp = 0
        self._in_flight_orders = {}  # Dict[client_order_id:str, idexComInFlightOrder]
        self._order_not_found_records = {}  # Dict[client_order_id:str, count:int]
        self._trading_rules = {}  # Dict[trading_pair:str, TradingRule]
        self._status_polling_task = None
        self._user_stream_event_listener_task = None
        self._trading_rules_polling_task = None
        self._last_poll_timestamp = 0

    @property
    def tracking_states(self) -> Dict[str, any]:
        """
        :return active in-flight orders in json format, is used to save in sqlite db.
        """
        return {
            key: value.to_json()
            for key, value in self._in_flight_orders.items()
            if not value.is_done
        }

    def supported_order_types(self) -> List[OrderType]:
        # TODO: Validate against
        """
        0	Market
        1	Limit
        2	Limit maker
        3	Stop loss
        4	Stop loss limit
        5	Take profit
        6	Take profit limit
        :return:
        """
        return [OrderType.MARKET, OrderType.LIMIT, OrderType.LIMIT_MAKER]

    def start(self, clock: Clock, timestamp: float):
        """
        This function is called automatically by the clock.
        """
        super().start(clock, timestamp)

    def stop(self, clock: Clock):
        """
        This function is called automatically by the clock.
        """
        super().stop(clock)

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        return self._order_book_tracker.order_books

    @property
    def limit_orders(self) -> List[LimitOrder]:
        """
        TODO: Validate
        """
        return [
            in_flight_order.to_limit_order()
            for in_flight_order in self._in_flight_orders.values()
        ]

    async def get_active_exchange_markets(self) -> pd.DataFrame:
        """
        :return: data frame with trading_pair as index, and at least the following columns --
                 ["baseAsset", "quoteAsset", "volume", "USDVolume"]
        TODO: Validate that this method actually needed
        TODO: How to get USDVolume
        """
        pass

    def buy(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET, price: Decimal = s_decimal_NaN,
            **kwargs):
        order_id = create_id()
        safe_ensure_future(self._create_order("buy", order_id, trading_pair, amount, order_type, price))
        return order_id

    def sell(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET, price: Decimal = s_decimal_NaN,
             **kwargs):
        order_id = create_id()
        safe_ensure_future(self._create_order("sell", order_id, trading_pair, amount, order_type, price))
        return order_id

    async def _create_order(self,
                            side: OrderSide,
                            order_id: str,
                            trading_pair: str,
                            amount: Decimal,
                            order_type=OrderType.MARKET,
                            price: Decimal = s_decimal_NaN):
        market = await to_idex_pair(trading_pair)
        await self._client.trade.create_order(
            parameters=RestRequestOrder(
                wallet="None",  # TODO: Get wallet
                clientOrderId=order_id,
                market=market,
                quantity=str(amount),
                type=to_idex_order_type(order_type),
                price=str(price),
                side=side
            )
        )

    def get_order_price_quantum(self, trading_pair: str, price: Decimal) -> Decimal:
        return Decimal(0.00000001)

    def get_order_size_quantum(self, trading_pair: str, order_size: Decimal) -> Decimal:
        return Decimal(0.00000001)

    def start_tracking_order(self,
                             order_id: str,
                             exchange_order_id: str,
                             trading_pair: str,
                             trade_type: TradeType,
                             price: Decimal,
                             amount: Decimal,
                             order_type: OrderType):
        """
        Starts tracking an order by simply adding it into _in_flight_orders dictionary.
        """
        self._in_flight_orders[order_id] = IdexInFlightOrder(
            client_order_id=order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            order_type=order_type,
            trade_type=trade_type,
            price=price,
            amount=amount
        )

    def cancel(self, trading_pair: str, client_order_id: str):
        safe_ensure_future(self._cancel_order(trading_pair, client_order_id))

    async def _cancel_order(self, trading_pair: str, client_order_id: str):
        market = await to_idex_pair(trading_pair)
        await self._client.trade.cancel_order(parameters=RestRequestCancelOrder(
            wallet="None",  # TODO: Get wallet
            orderId=client_order_id,
            market=market
        ))

    async def get_order(self, client_order_id: str) -> Dict[str, Any]:
        order = self._in_flight_orders.get(client_order_id)
        exchange_order_id = await order.get_exchange_order_id()
        orders = await self._client.trade.get_order(orderId=exchange_order_id)
        return [asdict(order) for order in orders] if isinstance(orders, list) else asdict(orders)

    def get_order_book(self, trading_pair: str) -> OrderBook:
        if trading_pair not in self._order_book_tracker.order_books:
            raise ValueError(f"No order book exists for '{trading_pair}'.")
        return self._order_book_tracker.order_books[trading_pair]

    async def check_network(self) -> NetworkStatus:
        try:
            result = await self._client.public.get_ping()
            assert result == {}
        except asyncio.CancelledError:
            raise
        except Exception:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    async def start_network(self):
        """
        TODO: _status_polling_loop
        :return:
        """
        await self.stop_network()
        self._order_book_tracker.start()

    async def stop_network(self):
        self._order_book_tracker.stop()

    def get_fee(self,
                base_currency: str,
                quote_currency: str,
                order_type: OrderType,
                order_side: TradeType,
                amount: Decimal,
                price: Decimal = s_decimal_NaN) -> TradeFee:
        return estimate_fee(EXCHANGE_NAME, order_type == TradeType.BUY)

    @property
    def status_dict(self) -> Dict[str, bool]:
        return {
            "order_books_initialized": self._order_book_tracker.ready,
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0,
            "user_stream_initialized":
                self._user_stream_tracker.data_source.last_recv_time > 0 if self._trading_required else True,
        }

    @property
    def ready(self) -> bool:
        return all(self.status_dict.values())

    @property
    def in_flight_orders(self)  -> Dict[str, InFlightOrderBase]:
        return self._in_flight_orders

    async def cancel_all(self, timeout_seconds: float):
        """
                Cancels all in-flight orders and waits for cancellation results.
                Used by bot's top level stop and exit commands (cancelling outstanding orders on exit)
                :param timeout_seconds: The timeout at which the operation will be canceled.
                :returns List of CancellationResult which indicates whether each order is successfully cancelled.
                """
        incomplete_orders = [o for o in self._in_flight_orders.values() if not o.is_done]
        tasks = [self._execute_cancel(o.trading_pair, o.client_order_id, True) for o in incomplete_orders]
        order_id_set = set([o.client_order_id for o in incomplete_orders])
        successful_cancellations = []
        try:
            async with timeout(timeout_seconds):
                results = await safe_gather(*tasks, return_exceptions=True)
                for result in results:
                    if result is not None and not isinstance(result, Exception):
                        order_id_set.remove(result)
                        successful_cancellations.append(CancellationResult(result, True))
        except Exception:
            self.logger().error("Cancel all failed.", exc_info=True)
            self.logger().network(
                "Unexpected error cancelling orders.",
                exc_info=True,
                app_warning_msg="Failed to cancel order on Crypto.com. Check API key and network connection."
            )

        failed_cancellations = [CancellationResult(oid, False) for oid in order_id_set]
        return successful_cancellations + failed_cancellations

    def stop_tracking_order(self, order_id: str):
        if order_id in self._in_flight_orders:
            del self._in_flight_orders[order_id]

    _account_available_balances = None
    _account_balances = None

    async def _update_balances(self):
        self._account_available_balances = self._account_available_balances or {}
        self._account_balances = self._account_balances or {}
        balances_available = {}
        balances = {}
        wallets = await self._client.user.wallets()
        for wallet in wallets:
            accounts = await self._client.user.balances(wallet.address)
            for account in accounts:
                # Set available balance
                balances_available.setdefault(wallet, {})
                balances_available[wallet][account.asset] = Decimal(account.availableForTrade)
                # Set balance
                balances.setdefault(wallet, {})
                balances[wallet][account.asset] = Decimal(account.quantity)

        self._account_available_balances = balances_available
        self._account_balances = balances
