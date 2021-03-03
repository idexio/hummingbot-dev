import asyncio
import aiohttp
import unittest

from typing import List
from unittest.mock import patch

from test.integration.assets.mock_data.fixture_idex import FixtureIdex
from hummingbot.connector.exchange.idex.idex_api_order_book_data_source import IdexAPIOrderBookDataSource


class TestDataSource (unittest.TestCase):

    trading_pairs: List[str] = [
        "UNI-ETH",
        "BAL-ETH",
        "PIP-ETH"
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.order_book_data_source: IdexAPIOrderBookDataSource = IdexAPIOrderBookDataSource(cls.trading_pairs)
        cls.idex_rest_url: str = IdexAPIOrderBookDataSource.get_idex_rest_url()
        print(cls.idex_rest_url)

    def run_async(self, task):
        return self.ev_loop.run_until_complete(task)

    def test_fetch_trading_pairs(self):
        trading_pairs: List[str] = self.run_async(self.order_book_data_source.fetch_trading_pairs())
        self.assertIn("UNI-ETH", trading_pairs)