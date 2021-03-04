import asyncio
import aiohttp
import unittest

from typing import List
from unittest.mock import patch
from unittest.mock import PropertyMock

from test.integration.assets.mock_data.fixture_idex import FixtureIdex
from hummingbot.connector.exchange.idex.idex_api_order_book_data_source import IdexAPIOrderBookDataSource


class TestDataSource (unittest.TestCase):

    eth_trading_pairs: List[str] = [
        "UNI-ETH",
        "LBA-ETH"
    ]

    bsc_trading_pairs: List[str] = [
        "EOS-USDT",
        "BTCB-BNB"
    ]


    @classmethod
    def setUpClass(cls) -> None:
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.eth_order_book_data_source: IdexAPIOrderBookDataSource = IdexAPIOrderBookDataSource(cls.eth_sample_pairs)
        cls.bsc_order_book_data_source: IdexAPIOrderBookDataSource = IdexAPIOrderBookDataSource(cls.bsc_sample_pairs)
        cls.REST_URL: str = 'hummingbot.connector.exchange.idex.idex_api_order_book_data_source.IdexAPIOrderBookDataSource._IDEX_REST_URL'
        cls.WS_FEED: str = 'hummingbot.connector.exchange.idex.idex_api_order_book_data_source.IdexAPIOrderBookDataSource._IDEX_WS_FEED'


    def run_async(self, task):
        return self.ev_loop.run_until_complete(task)

    # Test returns: Success
    # Uses PropertyMock to mock the API URL. Serves more to validate the use of PropertyMock in functions with GET requests to the URL.
    # The appropriate means of testing access to the global_config_map blockchain value should be discussed.
    def test_get_idex_rest_url(self):
        with patch(self.REST_URL, new_callable=PropertyMock) as mocked_API_URL:
            # ETH URL
            mocked_API_URL.return_value = "https://api-eth.idex.io"
            #mocked_REST_URL.assert_called_with(blockchain=global_config_map['idex_contract_blockchain'].value)
            self.assertEqual("https://api-eth.idex.io", IdexAPIOrderBookDataSource.get_idex_rest_url())
            # BSC URL
            mocked_API_URL.return_value = "https://api-bsc.idex.io"
            #mocked_REST_URL.assert_called_with(blockchain=global_config_map['idex_contract_blockchain'].value)
            self.assertEqual("https://api-bsc.idex.io", IdexAPIOrderBookDataSource.get_idex_rest_url())

    # Test returns: Success
    # Uses PropertyMock to mock the WebSocket Feed. Serves more to validate the use of PropertyMock in functions with GET requests to the URL.
    # The appropriate means of testing access to the global_config_map blockchain value should be discussed.
    def test_get_idex_ws_feed(self):
        with patch(self.WS_FEED, new_callable=PropertyMock) as mocked_WS_FEED:
            # ETH URL
            mocked_WS_FEED.return_value = "wss://websocket-eth.idex.io/v1"
            #mocked_REST_URL.assert_called_with(blockchain=global_config_map['idex_contract_blockchain'].value)
            self.assertEqual("wss://websocket-eth.idex.io/v1", IdexAPIOrderBookDataSource.get_idex_ws_feed())
            # BSC URL
            mocked_WS_FEED.return_value = "wss://websocket-bsc.idex.io/v1"
            #mocked_REST_URL.assert_called_with(blockchain=global_config_map['idex_contract_blockchain'].value)
            self.assertEqual("wss://websocket-bsc.idex.io/v1", IdexAPIOrderBookDataSource.get_idex_ws_feed())

    # Test returns: Success
    # Uses PropertyMock to mock the API URL. Test confirms ability to fetch all trading pairs on both exchanges (ETH, BSC).
    def test_fetch_trading_pairs(self):
        with patch(self.REST_URL, new_callable=PropertyMock) as mocked_API_URL:
            # ETH URL
            mocked_API_URL.return_value = "https://api-eth.idex.io"
            trading_pairs: List[str] = self.run_async(
                self.eth_order_book_data_source.fetch_trading_pairs())
            self.assertIn("UNI-ETH", trading_pairs)
            self.assertIn("LBA-ETH", trading_pairs)
            #map(lambda sample_pair : self.assertIn(sample_pair, trading_pairs), self.eth_sample_pairs)
            # BSC URL
            mocked_API_URL.return_value = "https://api-bsc.idex.io"
            trading_pairs: List[str] = self.run_async(
                self.bsc_order_book_data_source.fetch_trading_pairs())
            self.assertIn("EOS-USDT", trading_pairs)
            self.assertIn("BTCB-BNB", trading_pairs)