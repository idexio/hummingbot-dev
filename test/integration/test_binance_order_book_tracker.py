#!/usr/bin/env python
import math
from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../../")))
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import OrderBookEvent, OrderBookTradeEvent, TradeType
from hummingbot.connector.exchange.binance.binance_order_book_tracker import BinanceOrderBookTracker
from hummingbot.connector.exchange.binance.binance_api_order_book_data_source import BinanceAPIOrderBookDataSource
import asyncio
import logging
from typing import (
    Dict,
    Optional,
    List,
)
import unittest

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)


class BinanceOrderBookTrackerUnitTest(unittest.TestCase):

    order_book_tracker: Optional[BinanceOrderBookTracker] = None
    events: List[OrderBookEvent] = [
        OrderBookEvent.TradeEvent
    ]
    trading_pairs: List[str] = [
        "BTCUSDT",
        "XRPUSDT"
    ]

    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.order_book_tracker: BinanceOrderBookTracker = BinanceOrderBookTracker(
            trading_pairs=cls.trading_pairs)
        cls.order_book_tracker_task: asyncio.Task = safe_ensure_future(cls.order_book_tracker.start())
        cls.ev_loop.run_until_complete(cls.wait_til_tracker_ready())

    @classmethod
    async def wait_til_tracker_ready(cls):
        while True:
            if len(cls.order_book_tracker.order_books) > 0:
                print("Initialized real-time order books.")
                return
            await asyncio.sleep(1)

    async def run_parallel_async(self, *tasks):
        future: asyncio.Future = safe_ensure_future(safe_gather(*tasks))
        while not future.done():
            await asyncio.sleep(1.0)
        return future.result()

    def run_parallel(self, *tasks):
        return self.ev_loop.run_until_complete(self.run_parallel_async(*tasks))

    def setUp(self):
        self.event_logger = EventLogger()
        for event_tag in self.events:
            for trading_pair, order_book in self.order_book_tracker.order_books.items():
                order_book.add_listener(event_tag, self.event_logger)

    def test_order_book_trade_event_emission(self):
        """
        Test if order book tracker is able to retrieve order book trade message from exchange and
        emit order book trade events after correctly parsing the trade messages
        """
        self.run_parallel(self.event_logger.wait_for(OrderBookTradeEvent))
        for ob_trade_event in self.event_logger.event_log:
            print(f"ob_trade_event: {ob_trade_event}")
            self.assertTrue(type(ob_trade_event) == OrderBookTradeEvent)
            self.assertTrue(ob_trade_event.trading_pair in self.trading_pairs)
            self.assertTrue(type(ob_trade_event.timestamp) == float)
            self.assertTrue(type(ob_trade_event.amount) == float)
            self.assertTrue(type(ob_trade_event.price) == float)
            self.assertTrue(type(ob_trade_event.type) == TradeType)
            self.assertTrue(math.ceil(math.log10(ob_trade_event.timestamp)) == 10)
            self.assertTrue(ob_trade_event.amount > 0)
            self.assertTrue(ob_trade_event.price > 0)

    def test_tracker_integrity(self):
        # Wait 5 seconds to process some diffs.
        self.ev_loop.run_until_complete(asyncio.sleep(10.0))
        order_books: Dict[str, OrderBook] = self.order_book_tracker.order_books
        btcusdt_book: OrderBook = order_books["BTCUSDT"]
        xrpusdt_book: OrderBook = order_books["XRPUSDT"]
        # print(btcusdt_book.snapshot)
        # print("xrpusdt")
        # print(xrpusdt_book.snapshot)
        self.assertGreaterEqual(btcusdt_book.get_price_for_volume(True, 10).result_price,
                                btcusdt_book.get_price(True))
        self.assertLessEqual(btcusdt_book.get_price_for_volume(False, 10).result_price,
                             btcusdt_book.get_price(False))
        self.assertGreaterEqual(xrpusdt_book.get_price_for_volume(True, 10000).result_price,
                                xrpusdt_book.get_price(True))
        self.assertLessEqual(xrpusdt_book.get_price_for_volume(False, 10000).result_price,
                             xrpusdt_book.get_price(False))
        for order_book in self.order_book_tracker.order_books.values():
            print(order_book.last_trade_price)
            self.assertFalse(math.isnan(order_book.last_trade_price))

    def test_api_get_last_traded_prices(self):
        binance_ob_data_source = BinanceAPIOrderBookDataSource(["BTCUSDT", "LTCBTC"])
        prices = self.ev_loop.run_until_complete(binance_ob_data_source.get_last_traded_prices(["BTCUSDT", "LTCBTC"]))
        for key, value in prices.items():
            print(f"{key} last_trade_price: {value}")
        self.assertGreater(prices["BTCUSDT"], 1000)
        self.assertLess(prices["LTCBTC"], 1)


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
