import json
import hmac
import uuid
import hashlib

from typing import Dict, Union
from urllib.parse import urlencode


class IdexAuth:

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def sign(self, data: Union[str, bytes]) -> str:
        return hmac.new(
            self.secret_key,
            data.encode("utf-8") if isinstance(data, str) else data,
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def generate_nonce():
        return str(uuid.uuid1())

    def generate_auth_dict(
            self,
            http_method: str,
            url: str,
            params: Dict[str, any],
            body: Dict[str, any]) -> Dict[str, any]:
        return getattr(self, f"generate_auth_dict_for_{http_method}")(url, params, body)

    def generate_auth_dict_for_get(
            self,
            url: str,
            params: Dict[str, any],
            body: Dict[str, any]) -> Dict[str, any]:

        if "nonce" not in params:
            params.update({
                "nonce": self.generate_nonce()
            })

        url = f"{url}?{urlencode(params)}"
        return {
            "headers": {
                "IDEX-API-Key": self.api_key,
                "IDEX-HMAC-Signature": self.sign(url)
            },
            "url": url
        }

    def generate_auth_dict_for_post(
            self,
            url: str,
            params: Dict[str, any],
            body: Dict[str, any]) -> Dict[str, any]:
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
            "body": body
        }

    generate_auth_dict_for_delete = generate_auth_dict_for_post
