import time
import asyncio
import aiohttp
import pandas as pd

from dataclasses import asdict
from typing import List, Dict, Any

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource

from .client.asyncio import AsyncIdexClient
from .utils import to_idex_pair
from .types.websocket.response import WebSocketResponseL2OrderBookShort, WebSocketResponseTradeShort


class IdexOrderBookTrackerDataSource(OrderBookTrackerDataSource):

    @classmethod
    async def get_last_traded_price(cls, pair: str) -> float:
        result = await AsyncIdexClient().market.get_tickers(
            market=to_idex_pair(pair)
        )
        if result:
            return float(result[0].close)

    @classmethod
    async def get_last_traded_prices(cls, trading_pairs: List[str]) -> Dict[str, float]:
        tasks = [cls.get_last_traded_price(pair) for pair in trading_pairs]
        results = await safe_gather(*tasks)
        return {pair: result for pair, result in zip(trading_pairs, results) if result}

    # @staticmethod
    # async def get_snapshot(client: aiohttp.ClientSession = None, trading_pair: str = None, limit: int = 1000) -> Dict[str, Any]:
    #     """
    #     TODO: Verify do we actully need to preserve Interface described in Dev Manual
    #
    #     :param client:
    #     :param trading_pair:
    #     :param limit:
    #     :return:
    #     """
    #     pair = to_idex_pair(trading_pair)
    #     client = AsyncIdexClient(session=client)
    #     orderbook =
    #     return asdict(orderbook)

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        client = AsyncIdexClient()
        snapshot = await client.market.get_orderbook(
            market=trading_pair,
            limit=1000
        )
        timestamp = time.time()
        snapshot_message = OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": trading_pair,
            "update_id": snapshot.sequence,
            "bids": snapshot.bids,
            "asks": snapshot.asks
        }, timestamp=timestamp)

        order_book = self.order_book_create_function()
        order_book.apply_snapshot(
            snapshot_message.bids,
            snapshot_message.asks,
            snapshot_message.update_id
        )
        return order_book

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        while True:
            try:
                client = AsyncIdexClient()
                async for message in client.subscribe(  # type: WebSocketResponseL2OrderBookShort
                        subscriptions=["l2orderbook"],
                        message_cls=WebSocketResponseL2OrderBookShort):
                    timestamp = message.t
                    # TODO: Verify message
                    order_book_message = OrderBookMessage(OrderBookMessageType.DIFF, {
                        "trading_pair": message.m,
                        "update_id": message.u,
                        "bids": message.b,
                        "asks": message.a
                    }, timestamp=timestamp)
                    output.put_nowait(order_book_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error with WebSocket connection. Retrying after 30 seconds...",
                    exc_info=True
                )
                await asyncio.sleep(30.0)

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        while True:
            try:
                client = AsyncIdexClient()
                for trading_pair in self._trading_pairs:
                    try:
                        snapshot = await client.market.get_orderbook(
                            market=trading_pair
                        )
                        timestamp = time.time()
                        snapshot_message = OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
                            "trading_pair": trading_pair,
                            "update_id": snapshot.sequence,
                            "bids": snapshot.bids,
                            "asks": snapshot.asks,
                        }, timestamp=timestamp)
                        output.put_nowait(snapshot_message)
                        self.logger().debug(f"Saved order book snapshot for {trading_pair}")
                        # Be careful not to go above Binance's API rate limits.
                        await asyncio.sleep(5.0)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.logger().error("Unexpected error.", exc_info=True)
                        await asyncio.sleep(5.0)
                this_hour: pd.Timestamp = pd.Timestamp.utcnow().replace(minute=0, second=0, microsecond=0)
                next_hour: pd.Timestamp = this_hour + pd.Timedelta(hours=1)
                delta: float = next_hour.timestamp() - time.time()
                await asyncio.sleep(delta)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error.", exc_info=True)
                await asyncio.sleep(5.0)

    async def listen_for_trades(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        while True:
            try:
                client = AsyncIdexClient()
                async for message in client.subscribe(  # type: WebSocketResponseTradeShort
                        subscriptions=["trade"],
                        markets=[to_idex_pair(pair) for pair in self._trading_pairs],
                        message_cls=WebSocketResponseTradeShort):
                    timestamp = message.t
                    trade_message = OrderBookMessage(OrderBookMessageType.TRADE, {
                        "trading_pair": message.m,
                        # "trade_type": float(TradeType.SELL.value) if msg["m"] else float(TradeType.BUY.value),
                        "trade_type": message.s,  # TODO: convert
                        "trade_id": message.u,  # TODO: check i and u
                        "update_id": message.i,
                        "price": message.p,
                        "amount": message.q  # TODO: check against Q
                    }, timestamp=timestamp * 1e-3)
                    output.put_nowait(trade_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error with WebSocket connection. Retrying after 30 seconds...",
                                    exc_info=True)
                await asyncio.sleep(30.0)  # TODO: sleep timeout ?
