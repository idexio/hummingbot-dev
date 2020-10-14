import asyncio

from decimal import Decimal
from typing import Optional, List

from hummingbot.connector.exchange.idex.client.asyncio import AsyncIdexClient
from hummingbot.connector.exchange.idex.idex_auth import IdexAuth
from hummingbot.connector.exchange.idex.idex_order_book_tracker import IdexOrderBookTracker
from hummingbot.connector.exchange.idex.types.rest.request import RestRequestCancelOrder, RestRequestOrder, OrderSide
from hummingbot.connector.exchange.idex.utils import to_idex_pair, to_idex_order_type, create_id
from hummingbot.connector.exchange_base import ExchangeBase, s_decimal_NaN
from hummingbot.core.event.events import OrderType, TradeType
from hummingbot.core.utils.async_utils import safe_ensure_future


class IdexExchange(ExchangeBase):

    def __init__(self,
                 idex_com_api_key: str,
                 idex_com_secret_key: str,
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
        self._idex_auth: IdexAuth = IdexAuth(idex_com_api_key, idex_com_secret_key)
        self._client: AsyncIdexClient = AsyncIdexClient(auth=self._idex_auth)
        self._order_book_tracker = IdexOrderBookTracker(trading_pairs=trading_pairs)
        # TODO: self._user_stream_tracker = idexComUserStreamTracker(self._idex_com_auth, trading_pairs)
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
    def order_books(self):
        pass

    @property
    def limit_orders(self):
        pass

    async def get_active_exchange_markets(self):
        pass

    def c_stop_tracking_order(self, order_id):
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

    def cancel(self, trading_pair: str, client_order_id: str):
        safe_ensure_future(self._cancel_order(trading_pair, client_order_id))

    async def _cancel_order(self, trading_pair: str, client_order_id: str):
        market = await to_idex_pair(trading_pair)
        await self._client.trade.cancel_order(parameters=RestRequestCancelOrder(
            wallet="None",  # TODO: Get wallet
            orderId=client_order_id,
            market=market
        ))

    def get_order_book(self, trading_pair: str):
        pass

    def get_fee(self, base_currency: str, quote_currency: str, order_type: OrderType, order_side: TradeType,
                amount: Decimal, price: Decimal = s_decimal_NaN):
        pass

    @property
    def status_dict(self):
        pass

    @property
    def ready(self):
        pass

    @property
    def in_flight_orders(self):
        pass

    async def cancel_all(self, timeout_seconds: float):
        pass

    def stop_tracking_order(self, order_id: str):
        pass
