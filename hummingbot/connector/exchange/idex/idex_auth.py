import json
import hmac
import string
import uuid
import hashlib

from typing import Dict, Union
from urllib.parse import urlencode

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from hummingbot.connector.exchange.idex.conf import settings
from hummingbot.core.event.events import OrderType, TradeType


class IdexAuth:

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def sign(self, data: Union[str, bytes]) -> str:
        return hmac.new(
            self.secret_key.encode("utf-8") if isinstance(self.secret_key, str) else self.secret_key,
            data.encode("utf-8") if isinstance(data, str) else data,
            hashlib.sha256
        ).hexdigest()

    HEX_DIGITS_SET = set(string.hexdigits)

    @classmethod
    def arrayif(cls, value: str):
        # Remove 0x
        value = value.rsplit("x", 1)[-1]
        # Filter none hex
        value = ''.join([c for c in value if c in cls.HEX_DIGITS_SET])
        # Split by 2
        value = [value[i:i + 2] for i in range(0, len(value), 2)]
        # Convert to array
        return list(map(lambda v: int(v, 16), value))

    @classmethod
    def hex_to_uint128(cls, value):
        # Remove 0x
        value = value.rsplit("x", 1)[-1]
        # Filter none hex
        value = ''.join([c for c in value if c in cls.HEX_DIGITS_SET])
        return int(value, 16)

    def sign_wallet(self,
                    nonce: str,
                    wallet: str,
                    market: str,
                    order_type: OrderType,
                    order_side: TradeType,
                    order_quantity: str,
                    order_price: str = None,
                    order_stop_price: str = None,
                    order_custom_client_order_id: str = None,
                    order_time_in_force: int = None,
                    order_self_trade_trevention: int = None,
                    private_key: str = None):

        private_key = private_key or settings.eth_account_private_key

        parameters = [
            ["uint8", 1],
            ["uint128", self.hex_to_uint128(nonce)],
            ["address", wallet],
            ["string", market],
            ["uint8", order_type],
            ["uint8", order_side],
            ["string", order_quantity],
            ["bool", bool(order_quantity)],
            ["string", order_price or ""],
            ["string", order_stop_price or ""],
            ["string", order_custom_client_order_id or ""],
            ["uint8", order_time_in_force],
            ["uint8", order_self_trade_trevention or 0],
            ["uint64", 0]
        ]

        fields = [item[0] for item in parameters]
        values = [item[1] for item in parameters]

        signature_parameters_hash = Web3.solidityKeccak(fields, values)

        return Account.sign_message(
            signable_message=encode_defunct(text=signature_parameters_hash.hex()),
            private_key=private_key
        )

    @staticmethod
    def generate_nonce():
        return str(uuid.uuid1())

    def generate_auth_dict(
            self,
            http_method: str,
            url: str,
            params: Dict[str, any] = None,
            body: Dict[str, any] = None) -> Dict[str, any]:
        http_method = http_method.strip().lower()
        params = params or {}
        body = body or {}
        return getattr(self, f"generate_auth_dict_for_{http_method}")(url, params, body)

    def generate_auth_dict_for_get(
            self,
            url: str,
            params: Dict[str, any],
            body: Dict[str, any] = None) -> Dict[str, any]:

        if "nonce" not in params:
            params.update({
                "nonce": self.generate_nonce()
            })

        params = urlencode(params)
        url = f"{url}?{params}"
        return {
            "headers": {
                "IDEX-API-Key": self.api_key,
                "IDEX-HMAC-Signature": self.sign(params)
            },
            "url": url
        }

    def generate_auth_dict_for_post(
            self,
            url: str,
            params: Dict[str, any],
            body: Dict[str, any]) -> Dict[str, any]:
        body = body or {}
        parameters = body.get("parameters")
        if isinstance(parameters, dict) and "nonce" not in parameters:
            body["parameters"].update({
                "nonce": self.generate_nonce()
            })

        body = json.dumps(body)

        return {
            "headers": {
                "IDEX-API-Key": self.api_key,
                "IDEX-HMAC-Signature": self.sign(body)
            },
            "body": body,
        }

    generate_auth_dict_for_delete = generate_auth_dict_for_post
