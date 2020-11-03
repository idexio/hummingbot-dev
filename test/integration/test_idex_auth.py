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
        account = Account.from_key(
            b'\xba\xe6\x89\x00\x11\xb6N\xe2n\xe2\x82i,\x8e\xef\x073\x0f\xd8\xac\x10\x1d*\xe6\xcf\xa6\xac\xd3\x0f\x94\r\x01'
        )
        auth = IdexAuth(api_key="key_id", secret_key="key_secret")
        signature = auth.sign_wallet(
            nonce="5351ba18-1dd3-11eb-b0f2-0242ac110002",
            wallet=account.address,
            market="DIL-ETH",
            order_type=OrderType.MARKET.value,
            order_side=TradeType.BUY.value,
            order_quantity="1000.000000",
            order_price="200.000000",
            order_stop_price="150.000000",
            order_custom_client_order_id="123",
            order_time_in_force=123321321,
            order_self_trade_trevention=None,
            private_key=account.privateKey
        )

        print(auth.generate_nonce())
        print(int(time.time() - 100))
        print(signature.messageHash)
        print(signature.signature)

        self.assertEqual(
            signature.messageHash,
            b'\xdd\xfa\x8c\x96<\xca\xc9\xc0\xc6\xe2@!\r\x00\xba\x0e!\xad<dx\x87lU\x95\x90PE\x95G\r\x00'
        )
        self.assertEqual(
            signature.signature,
            b"\xb2\x97\xf7\x05\xd0\xe3\t0g\xde\x94D\x88\x9a\xa5\x12\x07\xe9D\xfe\xc2\xd8\x07'\xa1*\x9a\xa2H\x1a`\x15K"
            b"\xf5\xab \x7f\xe0-K\x05\xec\x9f\x1d\xc8\x01;\x11=Y\xc5\x816\xb2\xabG\xcb\\\xe6\xe0]\x86\x9c\xa5\x1c"
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
