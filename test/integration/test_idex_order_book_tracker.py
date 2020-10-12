#!/usr/bin/env python
import math
import asyncio
import logging
import unittest

from os.path import join, realpath
import sys;

from hummingbot.connector.exchange.idex.idex_order_book_tracker import IdexOrderBookTracker

sys.path.insert(0, realpath(join(__file__, "../../../")))

from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import OrderBookEvent, OrderBookTradeEvent, TradeType

from typing import Dict, Optional, List

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)


class IdexOrderBookTrackerUnitTest(unittest.TestCase):

    order_book_tracker: Optional[IdexOrderBookTracker] = None
    events: List[OrderBookEvent] = [
        OrderBookEvent.TradeEvent
    ]
    trading_pairs: List[str] = [
        "DIL-ETH",
        "PIP-ETH"
    ]

    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.order_book_tracker: IdexOrderBookTracker = IdexOrderBookTracker(
            trading_pairs=cls.trading_pairs
        )
        cls.order_book_tracker_task: asyncio.Task = safe_ensure_future(cls.order_book_tracker.start())
        cls.ev_loop.run_until_complete(cls.wait_til_tracker_ready())

    @classmethod
    async def wait_til_tracker_ready(cls):
        while True:
            if len(cls.order_book_tracker.order_books) > 0:
                print("TEST: Initialized real-time order books.")
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
                print(f"SETUP: {locals()}")
                order_book.add_listener(event_tag, self.event_logger)

    def test_order_book_trade_event_emission(self):
        """
        Test if order book tracker is able to retrieve order book trade message from exchange and
        emit order book trade events after correctly parsing the trade messages
        """
        print("#1")
        self.run_parallel(self.event_logger.wait_for(OrderBookTradeEvent))
        print("#2")
        for ob_trade_event in self.event_logger.event_log:
            print(f"ob_trade_event: {ob_trade_event}")
            # self.assertTrue(type(ob_trade_event) == OrderBookTradeEvent)
            # self.assertTrue(ob_trade_event.trading_pair in self.trading_pairs)
            # self.assertTrue(type(ob_trade_event.timestamp) == float)
            # self.assertTrue(type(ob_trade_event.amount) == float)
            # self.assertTrue(type(ob_trade_event.price) == float)
            # self.assertTrue(type(ob_trade_event.type) == TradeType)
            # self.assertTrue(math.ceil(math.log10(ob_trade_event.timestamp)) == 10)
            # self.assertTrue(ob_trade_event.amount > 0)
            # self.assertTrue(ob_trade_event.price > 0)

    # def test_tracker_integrity(self):
    #     pass
    #
    # def test_api_get_last_traded_prices(self):
    #     pass


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
