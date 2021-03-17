#!/usr/bin/env python
# import os
from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../../")))

import asyncio
import logging
import unittest
# from decimal import Decimal
from urllib.parse import urljoin
from pprint import pformat
import aiohttp

# from typing import Optional

from hummingbot.connector.exchange.idex.idex_user_stream_tracker import IdexUserStreamTracker
from hummingbot.connector.exchange.idex.idex_exchange import IdexAuth  # , IdexExchange
# from hummingbot.connector.exchange.idex.idex_order_book_message import IdexOrderBookMessage

# from hummingbot.core.utils.async_utils import safe_ensure_future
# from hummingbot.connector.exchange.idex.idex_order_book_tracker import IdexOrderBookTracker
# from hummingbot.core.event.events import OrderType

logging.basicConfig(level=logging.DEBUG)


class IdexOrderBookTrackerUnitTest(unittest.TestCase):
    # order_book_tracker: Optional[IdexOrderBookTracker] = None
    IDEX_API_KEY = ""
    IDEX_SECRET_KEY = ""
    IDEX_PRIVATE_KEY = "not this time! ;P"  # don't commit me please

    # first_order = OrderType.LIMIT?
    base_url = 'https://api-sandbox-eth.idex.io/'  # rest url for sandbox (rinkeby) ETH chain
    idex_auth = IdexAuth(
        api_key=IDEX_API_KEY,
        secret_key=IDEX_SECRET_KEY,
        wallet_private_key=IDEX_PRIVATE_KEY,
        # trading_pairs=["DIL-ETH", "PIP-ETH", "CUR-ETH"],
        # trading_required=True,
    )

    def create_test_order(self):
        """
        Tests create order to check trade level authentication (HMAC Header + ETH Wallet signature)
        with request: POST /v1/orders
        """
        path = '/v1/orders'
        url = urljoin(self.base_url, path)

        self.idex_auth.generate_nonce()  # re create nonce before each request

        order = {
            'nonce': self.idex_auth.get_nonce_str(),  # example: "9436afa0-9ee6-11ea-8a53-71994564322f",
            'wallet': self.idex_auth.get_wallet_address(),  # example: "0xA71C4aeeAabBBB8D2910F41C2ca3964b81F7310d"
            'market': 'DIL-ETH',
            'type': 0,  # enum value for market orders
            'side': 0,  # enum value for buy
            'quoteOrderQuantity': '100.00000000',
        }

        signature_parameters = (  # see idex doc: https://docs.idex.io/#associate-wallet
            ('uint8', 1),  # 0 - The signature hash version is 1 for Ethereum, 2 for BSC

            ('uint128', self.idex_auth.get_nonce_int()),  # 1 - Nonce
            ('address', order['wallet']),  # 2 - Signing wallet address
            ('string', order['market']),  # 3 - Market symbol (e.g. ETH-USDC)
            ('uint8', order['type']),  # 4 - Order type enum value
            ('uint8', order['side']),  # 5 - Order side enum value

            ('string', order['quoteOrderQuantity']),  # 6 - Order quantity in base or quote terms
            ('bool', True),  # 7 - false if order quantity in base terms; true if order quantity in quote terms
            ('string', ''),  # 8 - Order price or empty string if market order
            ('string', ''),  # 9 - Order stop price or empty string if not a stop loss or take profit order

            ('string', ''),  # 10 - Client order id or empty string
            ('uint8', 0),  # 11 - Order time in force enum value
            ('uint8', 0),  # 12 - Order self-trade prevention enum value
            ('uint64', 0),  # 13 - Unused, always should be 0
        )
        wallet_signature = self.idex_auth.wallet_sign(signature_parameters)

        payload = {
            "parameters": {
                'nonce': order['nonce'],  # example: "9436afa0-9ee6-11ea-8a53-71994564322f",
                'wallet': order['wallet'],  # example: "0xA71C4aeeAabBBB8D2910F41C2ca3964b81F7310d"
                "market": order['market'],
                "type": "market",  # todo: declare enums
                "side": "buy",
                "quoteOrderQuantity": order['quoteOrderQuantity']
            },
            'signature': wallet_signature,
        }

        print('payload:\n', pformat(payload))

        auth_dict = self.idex_auth.generate_auth_dict(http_method='POST', url=url, body=payload)

        print('auth_dict:\n', pformat(auth_dict))

        status, response = self.ev_loop.run_until_complete(
            self.rest_post(auth_dict['url'], payload, headers=auth_dict['headers'])
        )
        print('response:\n', pformat(response))

        if status == 200:
            # check order was correctly placed (if partially filled you get status: cancelled)
            self.assertIsInstance(response, dict)
            self.assertEqual(set(response.keys()), set(self.example_response_market_order_partially_filled))
            # note: curious behavior observed: even if account has insufficient funds, an order can sometimes be placed
            # and you get get response back which lacks fields: avgExecutionPrice and fills
        elif status == 402:  # HTTP 402: Payment Required. Error due to lack of funds
            self.assertIsInstance(response, dict) and self.assertEqual(set(response.keys()), {'code', 'message'})
            self.assertEqual('INSUFFICIENT_FUNDS', response['code'])
            self.fail(msg="Test account has insufficient funds to run the test")  # make test fail for awareness
        else:
            self.assertEqual(status, 200, msg=f'Unexpected error when creating order. Response: {response}')

    async def rest_post(self, url, payload, headers=None, params=None):
        async with aiohttp.ClientSession() as client:
            async with client.post(url, json=payload, headers=headers, params=params) as resp:
                # assert resp.status == 200
                print(resp.status)
                body = await resp.json()
                return resp.status, body

    @classmethod
    def setUpClass(cls):
        print("setup")
        IDEX_API_KEY = "tkDey53dr1ZlyM2tzUAu82l+nhgzxCJl"
        IDEX_SECRET_KEY = "889fe7dd-ea60-4bf4-86f8-4eec39146510"
        IDEX_PRIVATE_KEY = "0227070369c04f55c66988ee3b272f8ae297cf7967ca7bad6d2f71f72072e18d"  # don't commit me please

        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.user_stream_tracker: IdexUserStreamTracker = IdexUserStreamTracker(
            # idex_auth=IdexAuth(
            #     api_key=os.getenv("IDEX_API_KEY"),
            #     secret_key=os.getenv("IDEX_SECRET_KEY"),
            #     wallet_private_key=os.getenv("IDEX_PRIVATE_KEY"),
            # )
            idex_auth=IdexAuth(
                api_key=IDEX_API_KEY,
                secret_key=IDEX_SECRET_KEY,
                wallet_private_key=IDEX_PRIVATE_KEY,
                # trading_pairs=["DIL-ETH", "PIP-ETH", "CUR-ETH"],
                # trading_required=True,
            )
        )
        # cls.market: IdexExchange = IdexExchange(self.IDEX_API_KEY,
        #                                         self.IDEX_SECRET_KEY,
        #                                         self.IDEX_PRIVATE_KEY,
        #                                         ["DIL-ETH", "PIP-ETH", "CUR-ETH"],
        #                                         True
        #                                         )

    # @unittest.skip

    def test_user_stream_manually(self):
        """
        This test should be run before market functions like buy and sell are implemented.
        Developer needs to manually trigger those actions in order for the messages to show up in the user stream.
        """
        # self.ev_loop.run_until_complete(asyncio.sleep(10.0))
        # print(self.user_stream_tracker.user_stream)
        print("Make an order then see if it shows up")
        print("goals: see if balances go through, create a second order, cancel an order")
        # cls.user_stream_tracker_task: asyncio.Task = safe_ensure_future(cls.user_stream_tracker.start())
        self.create_test_order()


def main():
    print("MAIN!!!!!!!!!!!!!!!")
    unittest.main()


if __name__ == "__main__":
    main()
