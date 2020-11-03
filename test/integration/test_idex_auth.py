#!/usr/bin/env python
import logging
import time
import unittest

from os.path import join, realpath
import sys

from eth_account import Account

from hummingbot.connector.exchange.idex.idex_auth import IdexAuth
from hummingbot.core.event.events import OrderType, TradeType

sys.path.insert(0, realpath(join(__file__, "../../../")))


class IdexAuthUnitTest(unittest.TestCase):

    def test_get_signature(self):
        auth = IdexAuth(api_key="key_id", secret_key="key_secret")
        result = auth.generate_auth_dict(
            http_method="get",
            url="https://url.com/",
            params={"foo": "bar", "nonce": "2c1b41ae-0eeb-11eb-971f-0242ac110002"}
        )
        self.assertEqual(result["headers"]["IDEX-API-Key"], "key_id")
        self.assertEqual(
            result["headers"]["IDEX-HMAC-Signature"],
            "a55857025516a8b0f71ab80efeb5e15d5f52d48574c008b7663292eb1417d5bd"
        )
        self.assertIn("nonce", result["url"])

    def test_wallet_signature(self):
        account = Account.create()

        auth = IdexAuth(api_key="key_id", secret_key="key_secret")
        signature = auth.sign_wallet(
            nonce=auth.generate_nonce(),
            wallet=account.address,
            market="DIL-ETH",
            order_type=OrderType.MARKET.value,
            order_side=TradeType.BUY.value,
            order_quantity="1000.000000",
            order_price="200.000000",
            order_stop_price="150.000000",
            order_custom_client_order_id="123",
            order_time_in_force=int(time.time() - 100),
            order_self_trade_trevention=None,
            private_key=account.privateKey
        )

        self.assertEqual(
            signature.messageHash,
            b'\x0e\xd1\x00\xd3\xd9\xf3\xb6sx\xd2\x1c\x07\x1b.yU\xdd$n\xc7\xcd\x15\x81\xefK\xe1@\xd9\xa8\xda9|'
        )
        self.assertEqual(
            signature.signature,
            b'\\ro2\xbf\x9a\x95cb\xbd\xe87M_p\xba\xf0\x7f\x15~At)\xedp9\x11]\x80\x10\xd2t\x12_\xac\xa9\x15\xa2T\x90\xf7'
            b'\xd9\x95d\x00\xbc\x17d\xf3\xc2%\xad\xbc\xa2\xcc\xb8\xbb^\x97\xec\x82\xefSh\x1c'
        )

    def test_post_signature(self):
        auth = IdexAuth(api_key="key_id", secret_key="key_secret")
        result = auth.generate_auth_dict(
            http_method="post",
            url="https://url.com/",
            body={
                "parameters": {
                    "foo": "bar",
                    "nonce": "2c1b41ae-0eeb-11eb-971f-0242ac110002"
                }
            }
        )
        self.assertEqual(result["headers"]["IDEX-API-Key"], "key_id")
        self.assertEqual(
            result["headers"]["IDEX-HMAC-Signature"],
            "8829de6a69590fe5311d27370a848f6dbc230137bc4f9aadd7f8c633770a77d3"
        )
        self.assertIn("nonce", result["body"])


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
