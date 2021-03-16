import time
import asyncio
import logging
import aiohttp
from typing import (
    AsyncIterable,
    Dict,
    Optional,
    List,
)

import ujson
import websockets
from websockets.exceptions import ConnectionClosed

from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger

# from .client.asyncio import AsyncIdexClient
from .idex_auth import IdexAuth
# from .utils import get_markets
IDEX_WS_FEED = "wss://websocket-eth.idex.io/v1"
IDEX_REST_URL = "https://api-eth.idex.io/"
# TODO: elliott-- to v1 or not to v1,
# also declaring of these instead of config mapping??


class IdexAPIUserStreamDataSource(UserStreamTrackerDataSource):
    MAX_RETRIES = 20
    MESSAGE_TIMEOUT = 30.0

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        cls._logger = cls._logger or logging.getLogger(__name__)
        return cls._logger

    def __init__(self, idex_auth: IdexAuth, trading_pairs: Optional[List[str]] = []):
        self._idex_auth = idex_auth
        self._trading_pairs = trading_pairs
        self._current_listen_key = None
        self._listen_for_user_stream_task = None
        self._last_recv_time: float = 0
        self.sub_token: str = ""
        super(IdexAPIUserStreamDataSource, self).__init__()

    @property
    def last_recv_time(self) -> float:
        return self._last_recv_time

    async def get_ws_auth_token(self) -> str:
        user_wallet_address = IdexAuth.get_wallet_address()
        # TODO: elliott-- make ws auth dict token (better)
        auth_dict: Dict[str] = self._idex_auth.auth_for_ws("/wsToken", "", user_wallet_address)

        # token required for balances and orders
        async with aiohttp.ClientSession() as client:
            resp = await client.get(f"{IDEX_REST_URL}/v1/wsToken?{auth_dict}")  # TODO: Elliott-- ugly

            resp_json = await resp.json()

            return resp_json["token"]

    async def listen_for_user_stream(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        """
        Path subscription notation: wss://websocket-{blockchain}.idex.io/v1/{market}@{subscription}_{option}
        Example for 15m market tickers from ETH-USDC
        :blockchain: eth
        :option: 15m
        :subcription: ticker
        :market: ETH-USDC
                Example subscribe JSON:
        {
            "method": "subscribe",
            "markets": ["ETH-USDC", "IDEX-ETH"],
            "subscriptions": [
                "tickers",
                "trades"
            ]
        }

        """

        while True:
            try:
                async with websockets.connect(IDEX_WS_FEED) as ws:
                    ws: websockets.WebSocketClientProtocol = ws
                    subscribe_request: Dict[str, any] = {
                        "method": "subscribe",
                        "markets": self._trading_pairs,
                        "subscriptions": ["orders", "trades", "balances"],
                    }

                    self.sub_token = self.get_ws_auth_token()

                    subscribe_request.update({"token": self.sub_token})
                    # TODO:  elliott -- check if auth_dict changed in new version

                    # send sub request
                    await ws.send(ujson.dumps(subscribe_request))

                    async for raw_msg in self._inner_messages(ws):
                        msg = ujson.loads(raw_msg)
                        msg_type: str = msg.get("type", None)
                        if msg_type is None:
                            raise ValueError(f"idex Websocket message does not contain a type - {msg}")
                        elif msg_type == "error":
                            raise ValueError(f"idex Websocket received error message - {msg['data']}")
                        elif msg_type in ["open", "match", "change", "done"]:
                            pass
                            # order_book_message: OrderBookMessage = self.order_book_class.diff_message_from_exchange(msg)
                            # output.put_nowait(order_book_message)

                        elif msg_type in ["balances", "orders", "trades"]:
                            # Users balances
                            # order_book_message: OrderBookMessage = self.order_book_class.diff_message_from_exchange(msg)
                            # output.put_nowait(order_book_message)

                            # asset = msg['data']['a']
                            # quantity = msg['data']['q']
                            pass  # TODO: elliott-- delete and send message

                        elif msg_type in ["ping"]:
                            # NOTE: ping every 3 min, closed if no pong after 10 min
                            pong_waiter = await ws.ping()
                            await pong_waiter

                        elif msg_type in ["received", "activate", "subscriptions"]:
                            # these messages are not needed to track the order book
                            pass
                        else:
                            raise ValueError(f"Unrecognized idex Websocket message received - {msg}")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error with Idex WebSocket connection. "
                                    "Retrying after 30 seconds...", exc_info=True)
                await asyncio.sleep(30.0)

    async def _inner_messages(self,
                              ws: websockets.WebSocketClientProtocol) -> AsyncIterable[str]:
        """
        Generator function that returns messages from the web socket stream
        :param ws: current web socket connection
        :returns: message in AsyncIterable format
        """
        # Terminate the recv() loop as soon as the next message timed out, so the outer loop can reconnect.
        try:
            while True:
                try:
                    msg: str = await asyncio.wait_for(ws.recv(), timeout=self.MESSAGE_TIMEOUT)
                    self._last_recv_time = time.time()
                    yield msg
                except asyncio.TimeoutError:
                    try:
                        pong_waiter = await ws.ping()
                        self._last_recv_time = time.time()
                        await asyncio.wait_for(pong_waiter, timeout=self.PING_TIMEOUT)
                    except asyncio.TimeoutError:
                        raise
        except asyncio.TimeoutError:
            self.logger().warning("WebSocket ping timed out. Going to reconnect...")
            return
        except ConnectionClosed:
            return
        finally:
            await ws.close()
