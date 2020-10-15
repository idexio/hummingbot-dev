#!/usr/bin/env python
import logging
import unittest

from os.path import join, realpath
import sys

from hummingbot.connector.exchange.idex.idex_auth import IdexAuth

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
