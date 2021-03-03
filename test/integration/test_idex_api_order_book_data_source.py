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

    def run_async(self, task):
        return self.ev_loop.run_until_complete(task)

    # Test returns:
    # Failure
    # >>  raise self.failureException("'ETH' != 'https://api-None.idex.io'\n- ETH\n+ https://api-None.idex.io\n")
    # get_idex_rest_url() returns url with blockchain = None when called.
    def test_get_idex_rest_url(self):
        self.assertEqual("ETH", IdexAPIOrderBookDataSource.get_idex_rest_url())

    # Test returns:
    # Failure
    # >> raise self.failureException("'UNI-ETH' not found in []")
    # test returns empty trading_pair list
    def test_fetch_trading_pairs(self):
        trading_pairs: List[str] = self.run_async(self.order_book_data_source.fetch_trading_pairs())
        self.assertIn("UNI-ETH", trading_pairs)