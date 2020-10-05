import asyncio
import time
from dataclasses import asdict

from typing import List, Dict, Any

import aiohttp

from hummingbot.hummingbot.connector.exchange.idex.client.asyncio import AsyncIdexClient
from hummingbot.hummingbot.connector.exchange.idex.utils import to_idex_pair
from hummingbot.hummingbot.core.data_type.order_book import OrderBook
from hummingbot.hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.hummingbot.core.utils.async_utils import safe_gather


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

    @staticmethod
    async def get_snapshot(client: aiohttp.ClientSession, trading_pair: str, limit: int = 1000) -> Dict[str, Any]:
        pair = to_idex_pair(trading_pair)
        client = AsyncIdexClient(session=client)
        orderbook = await client.market.get_orderbook(
            market=pair,
            limit=limit
        )
        return asdict(orderbook)

        # params: Dict = {"limit": str(limit), "symbol": convert_to_exchange_trading_pair(trading_pair)} if limit != 0 \
        #     else {"symbol": convert_to_exchange_trading_pair(trading_pair)}
        # async with client.get(SNAPSHOT_REST_URL, params=params) as response:
        #     response: aiohttp.ClientResponse = response
        #     if response.status != 200:
        #         raise IOError(f"Error fetching Binance market snapshot for {trading_pair}. "
        #                       f"HTTP status is {response.status}.")
        #     data: Dict[str, Any] = await response.json()
        #
        #     # Need to add the symbol into the snapshot message for the Kafka message queue.
        #     # Because otherwise, there'd be no way for the receiver to know which market the
        #     # snapshot belongs to.
        #
        #     return data

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        async with aiohttp.ClientSession() as client:
            snapshot = await self.get_snapshot(client, trading_pair, 1000)
            timestamp = time.time()
            snapshot_message= OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
                "trading_pair": trading_pair,
                "update_id": snapshot["sequence"],
                "bids": snapshot["bids"],
                "asks": snapshot["asks"]
            }, timestamp=timestamp)
            order_book = self.order_book_create_function()
            order_book.apply_snapshot(
                snapshot_message.bids,
                snapshot_message.asks,
                snapshot_message.update_id
            )
            return order_book

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        pass

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        pass

    async def listen_for_trades(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        pass
