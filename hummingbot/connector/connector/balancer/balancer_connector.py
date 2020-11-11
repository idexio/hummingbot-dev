import logging
from decimal import Decimal
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
import json
import time
import ssl
import copy
from hummingbot.logger.struct_logger import METRICS_LOG_LEVEL
from hummingbot.core.utils import async_ttl_cache
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.logger import HummingbotLogger
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.event.events import (
    MarketEvent,
    BuyOrderCreatedEvent,
    SellOrderCreatedEvent,
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
    MarketOrderFailureEvent,
    OrderFilledEvent,
    OrderType,
    TradeType,
    TradeFee
)
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.connector.connector.balancer.balancer_in_flight_order import BalancerInFlightOrder
from hummingbot.client.settings import GATEAWAY_CA_CERT_PATH, GATEAWAY_CLIENT_CERT_PATH, GATEAWAY_CLIENT_KEY_PATH
from hummingbot.core.utils.eth_gas_station_lookup import get_gas_price
from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.client.config.config_helpers import get_erc20_token_addresses

s_logger = None
s_decimal_0 = Decimal("0")
s_decimal_NaN = Decimal("nan")
logging.basicConfig(level=METRICS_LOG_LEVEL)


class BalancerConnector(ConnectorBase):
    """
    BalancerConnector connects with balancer gateway APIs and provides pricing, user account tracking and trading
    functionality.
    """
    API_CALL_TIMEOUT = 10.0
    POLL_INTERVAL = 60.0

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global s_logger
        if s_logger is None:
            s_logger = logging.getLogger(__name__)
        return s_logger

    def __init__(self,
                 trading_pairs: List[str],
                 wallet_private_key: str,
                 ethereum_rpc_url: str,
                 trading_required: bool = True
                 ):
        """
        :param trading_pairs: a list of trading pairs
        :param wallet_private_key: a private key for eth wallet
        :param ethereum_rpc_url: this is usually infura RPC URL
        :param trading_required: Whether actual trading is needed.
        """
        super().__init__()
        self._trading_pairs = trading_pairs
        tokens = set()
        for trading_pair in trading_pairs:
            tokens.update(set(trading_pair.split("-")))
        self._token_addresses = get_erc20_token_addresses(tokens)
        self._wallet_private_key = wallet_private_key
        self._ethereum_rpc_url = ethereum_rpc_url
        self._trading_required = trading_required
        self._ev_loop = asyncio.get_event_loop()
        self._shared_client = None
        self._last_poll_timestamp = 0.0
        self._in_flight_orders = {}
        self._allowances = {}
        self._status_polling_task = None
        self._auto_approve_task = None
        self._real_time_balance_update = False

    @property
    def name(self):
        return "balancer"

    @property
    def limit_orders(self) -> List[LimitOrder]:
        return [
            in_flight_order.to_limit_order()
            for in_flight_order in self._in_flight_orders.values()
        ]

    async def auto_approve(self):
        """
        Automatically approves Balancer contract as a spender for token in trading pairs.
        It first checks if there are any already approved amount (allowance)
        """
        self.logger().info("Checking for allowances...")
        self._allowances = await self.get_allowances()
        for token, amount in self._allowances.items():
            if amount <= s_decimal_0:
                amount_approved = await self.approve_balancer_spender(token)
                if amount_approved > 0:
                    self._allowances[token] = amount_approved
                    await asyncio.sleep(2)
                else:
                    break

    async def approve_balancer_spender(self, token_symbol: str) -> Decimal:
        """
        Approves Balancer contract as a spender for a token.
        :param token_symbol: token to approve.
        """
        resp = await self._api_request("post",
                                       "eth/approve",
                                       {"tokenAddress": self._token_addresses[token_symbol],
                                        "gasPrice": str(get_gas_price())})
        amount_approved = Decimal(str(resp["amount"]))
        if amount_approved > 0:
            self.logger().info(f"Approved Balancer spender contract for {token_symbol}.")
        else:
            self.logger().info(f"Balancer spender contract approval failed on {token_symbol}.")
        return amount_approved

    async def get_allowances(self) -> Dict[str, Decimal]:
        """
        Retrieves allowances for token in trading_pairs
        :return: A dictionary of token and its allowance (how much Balancer can spend).
        """
        ret_val = {}
        resp = await self._api_request("post", "eth/allowances",
                                       {"tokenAddressList": ",".join(self._token_addresses.values())})
        for address, amount in resp["approvals"].items():
            ret_val[self.get_token(address)] = Decimal(str(amount))
        return ret_val

    @async_ttl_cache(ttl=5, maxsize=10)
    async def get_quote_price(self, trading_pair: str, is_buy: bool, amount: Decimal) -> Optional[Decimal]:
        """
        Retrieves a quote price.
        :param trading_pair: The market trading pair
        :param is_buy: True for an intention to buy, False for an intention to sell
        :param amount: The amount required (in base token unit)
        :return: The quote price.
        """

        try:
            base, quote = trading_pair.split("-")
            side = "buy" if is_buy else "sell"
            resp = await self._api_request("post",
                                           f"balancer/{side}-price",
                                           {"base": self._token_addresses[base],
                                            "quote": self._token_addresses[quote],
                                            "amount": amount})
            if resp["price"] is not None:
                return Decimal(str(resp["price"]))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().network(
                f"Error getting quote price for {trading_pair}  {side} order for {amount} amount.",
                exc_info=True,
                app_warning_msg=str(e)
            )

    async def get_order_price(self, trading_pair: str, is_buy: bool, amount: Decimal) -> Decimal:
        """
        This is simply the quote price
        """
        return await self.get_quote_price(trading_pair, is_buy, amount)

    def buy(self, trading_pair: str, amount: Decimal, order_type: OrderType, price: Decimal) -> str:
        """
        Buys an amount of base token for a given price (or cheaper).
        :param trading_pair: The market trading pair
        :param amount: The order amount (in base token unit)
        :param order_type: Any order type is fine, not needed for this.
        :param price: The maximum price for the order.
        :return: A newly created order id (internal).
        """
        return self.place_order(True, trading_pair, amount, price)

    def sell(self, trading_pair: str, amount: Decimal, order_type: OrderType, price: Decimal) -> str:
        """
        Sells an amount of base token for a given price (or at a higher price).
        :param trading_pair: The market trading pair
        :param amount: The order amount (in base token unit)
        :param order_type: Any order type is fine, not needed for this.
        :param price: The minimum price for the order.
        :return: A newly created order id (internal).
        """
        return self.place_order(False, trading_pair, amount, price)

    def place_order(self, is_buy: bool, trading_pair: str, amount: Decimal, price: Decimal) -> str:
        """
        Places an order.
        :param is_buy: True for buy order
        :param trading_pair: The market trading pair
        :param amount: The order amount (in base token unit)
        :param price: The minimum price for the order.
        :return: A newly created order id (internal).
        """
        side = TradeType.BUY if is_buy else TradeType.SELL
        order_id = f"{side.name.lower()}-{trading_pair}-{get_tracking_nonce()}"
        safe_ensure_future(self._create_order(side, order_id, trading_pair, amount, price))
        return order_id

    async def _create_order(self,
                            trade_type: TradeType,
                            order_id: str,
                            trading_pair: str,
                            amount: Decimal,
                            price: Decimal):
        """
        Calls buy or sell API end point to place an order, starts tracking the order and triggers relevant order events.
        :param trade_type: BUY or SELL
        :param order_id: Internal order id (also called client_order_id)
        :param trading_pair: The market to place order
        :param amount: The order amount (in base token value)
        :param price: The order price
        """

        amount = self.quantize_order_amount(trading_pair, amount)
        price = self.quantize_order_price(trading_pair, price)
        base, quote = trading_pair.split("-")
        gas_price = get_gas_price()
        api_params = {"base": self._token_addresses[base],
                      "quote": self._token_addresses[quote],
                      "amount": str(amount),
                      "maxPrice": str(price),
                      "gasPrice": str(gas_price),
                      }
        self.start_tracking_order(order_id, None, trading_pair, trade_type, price, amount)
        try:
            order_result = await self._api_request("post", f"balancer/{trade_type.name.lower()}", api_params)
            hash = order_result["txHash"]
            status = order_result["status"]
            tracked_order = self._in_flight_orders.get(order_id)
            if tracked_order is not None:
                self.logger().info(f"Created {trade_type.name} order {order_id} txHash: {hash} "
                                   f"for {amount} {trading_pair}.")
                tracked_order.exchange_order_id = hash
            if int(status) == 1:
                tracked_order.fee_asset = "ETH"
                tracked_order.executed_amount_base = amount
                tracked_order.executed_amount_quote = amount * price
                tracked_order.fee_paid = Decimal(str(order_result["gasUsed"])) * gas_price / Decimal(str(1e9))
                event_tag = MarketEvent.BuyOrderCreated if trade_type is TradeType.BUY else MarketEvent.SellOrderCreated
                event_class = BuyOrderCreatedEvent if trade_type is TradeType.BUY else SellOrderCreatedEvent
                self.trigger_event(event_tag, event_class(self.current_timestamp, OrderType.LIMIT, trading_pair, amount,
                                                          price, order_id, hash))
                self.trigger_event(MarketEvent.OrderFilled,
                                   OrderFilledEvent(
                                       self.current_timestamp,
                                       tracked_order.client_order_id,
                                       tracked_order.trading_pair,
                                       tracked_order.trade_type,
                                       tracked_order.order_type,
                                       price,
                                       amount,
                                       TradeFee(0.0, [("ETH", tracked_order.fee_paid)]),
                                       hash
                                   ))

                event_tag = MarketEvent.BuyOrderCompleted if tracked_order.trade_type is TradeType.BUY \
                    else MarketEvent.SellOrderCompleted
                event_class = BuyOrderCompletedEvent if tracked_order.trade_type is TradeType.BUY \
                    else SellOrderCompletedEvent
                self.trigger_event(event_tag,
                                   event_class(self.current_timestamp,
                                               tracked_order.client_order_id,
                                               tracked_order.base_asset,
                                               tracked_order.quote_asset,
                                               tracked_order.fee_asset,
                                               tracked_order.executed_amount_base,
                                               tracked_order.executed_amount_quote,
                                               tracked_order.fee_paid,
                                               tracked_order.order_type))
                self.stop_tracking_order(tracked_order.client_order_id)
            else:
                self.trigger_event(MarketEvent.OrderFailure,
                                   MarketOrderFailureEvent(self.current_timestamp, order_id, OrderType.LIMIT))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.stop_tracking_order(order_id)
            self.logger().network(
                f"Error submitting {trade_type.name} order to Balancer for "
                f"{amount} {trading_pair} "
                f"{price}.",
                exc_info=True,
                app_warning_msg=str(e)
            )
            self.trigger_event(MarketEvent.OrderFailure,
                               MarketOrderFailureEvent(self.current_timestamp, order_id, OrderType.LIMIT))

    def start_tracking_order(self,
                             order_id: str,
                             exchange_order_id: str,
                             trading_pair: str,
                             trade_type: TradeType,
                             price: Decimal,
                             amount: Decimal):
        """
        Starts tracking an order by simply adding it into _in_flight_orders dictionary.
        """
        self._in_flight_orders[order_id] = BalancerInFlightOrder(
            client_order_id=order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=trade_type,
            price=price,
            amount=amount
        )

    def stop_tracking_order(self, order_id: str):
        """
        Stops tracking an order by simply removing it from _in_flight_orders dictionary.
        """
        if order_id in self._in_flight_orders:
            del self._in_flight_orders[order_id]

    def get_taker_order_type(self):
        return OrderType.LIMIT

    def get_order_price_quantum(self, trading_pair: str, price: Decimal) -> Decimal:
        return Decimal("1e-15")

    def get_order_size_quantum(self, trading_pair: str, order_size: Decimal) -> Decimal:
        return Decimal("1e-15")

    @property
    def ready(self):
        return all(self.status_dict.values())

    def has_allowances(self) -> bool:
        """
        Checks if all tokens have allowance (an amount approved)
        """
        return len(self._allowances.values()) == len(self._token_addresses.values()) and \
            all(amount > s_decimal_0 for amount in self._allowances.values())

    @property
    def status_dict(self) -> Dict[str, bool]:
        return {
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "allowances": self.has_allowances() if self._trading_required else True
        }

    async def start_network(self):
        if self._trading_required:
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            self._auto_approve_task = safe_ensure_future(self.auto_approve())

    async def stop_network(self):
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._auto_approve_task is not None:
            self._auto_approve_task.cancel()
            self._auto_approve_task = None

    async def check_network(self) -> NetworkStatus:
        try:
            response = await self._api_request("get", "api")
            if response["status"] != "ok":
                raise Exception(f"Error connecting to Gateway API. HTTP status is {response.status}.")
        except asyncio.CancelledError:
            raise
        except Exception:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    def tick(self, timestamp: float):
        """
        Is called automatically by the clock for each clock's tick (1 second by default).
        It checks if status polling task is due for execution.
        """
        if time.time() - self._last_poll_timestamp > self.POLL_INTERVAL:
            if not self._poll_notifier.is_set():
                self._poll_notifier.set()

    async def _status_polling_loop(self):
        while True:
            try:
                self._poll_notifier = asyncio.Event()
                await self._poll_notifier.wait()
                await safe_gather(
                    self._update_balances(),
                )
                self._last_poll_timestamp = self.current_timestamp
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(str(e), exc_info=True)
                self.logger().network("Unexpected error while fetching account updates.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch balances from Gateway API.")
                await asyncio.sleep(0.5)

    def get_token(self, token_address: str) -> str:
        return [k for k, v in self._token_addresses.items() if v == token_address][0]

    async def _update_balances(self):
        """
        Calls Eth API to update total and available balances.
        """
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()
        resp_json = await self._api_request("post",
                                            "eth/balances",
                                            {"tokenAddressList": ",".join(self._token_addresses.values())})
        for token, bal in resp_json["balances"].items():
            if len(token) > 4:
                token = self.get_token(token)
            self._account_available_balances[token] = Decimal(str(bal))
            self._account_balances[token] = Decimal(str(bal))
            remote_asset_names.add(token)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

        self._in_flight_orders_snapshot = {k: copy.copy(v) for k, v in self._in_flight_orders.items()}
        self._in_flight_orders_snapshot_timestamp = self.current_timestamp

    async def _http_client(self) -> aiohttp.ClientSession:
        """
        :returns Shared client session instance
        """
        if self._shared_client is None:
            ssl_ctx = ssl.create_default_context(cafile=GATEAWAY_CA_CERT_PATH)
            ssl_ctx.load_cert_chain(GATEAWAY_CLIENT_CERT_PATH, GATEAWAY_CLIENT_KEY_PATH)
            conn = aiohttp.TCPConnector(ssl_context=ssl_ctx)
            self._shared_client = aiohttp.ClientSession(connector=conn)
        return self._shared_client

    async def _api_request(self,
                           method: str,
                           path_url: str,
                           params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Sends an aiohttp request and waits for a response.
        :param method: The HTTP method, e.g. get or post
        :param path_url: The path url or the API end point
        :param params: A dictionary of required params for the end point
        :returns A response in json format.
        """
        base_url = f"https://{global_config_map['gateway_api_host'].value}:" \
                   f"{global_config_map['gateway_api_port'].value}"
        url = f"{base_url}/{path_url}"
        client = await self._http_client()
        if method == "get":
            if len(params) > 0:
                response = await client.get(url, params=params)
            else:
                response = await client.get(url)
        elif method == "post":
            params["privateKey"] = self._wallet_private_key
            if params["privateKey"][:2] != "0x":
                params["privateKey"] = "0x" + params["privateKey"]
            response = await client.post(url, data=params)

        parsed_response = json.loads(await response.text())
        if response.status != 200:
            err_msg = ""
            if "error" in parsed_response:
                err_msg = f" Message: {parsed_response['error']}"
            raise IOError(f"Error fetching data from {url}. HTTP status is {response.status}.{err_msg}")
        if "error" in parsed_response:
            raise Exception(f"Error: {parsed_response['error']}")

        return parsed_response

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        return []

    @property
    def in_flight_orders(self) -> Dict[str, BalancerInFlightOrder]:
        return self._in_flight_orders
