import os

from dataclasses import dataclass, fields


def inflect_env(s: "Settings"):
    for field in fields(s):
        env_value = os.getenv(f"IDEX_{field.name.upper()}")
        if not env_value:
            continue
        setattr(s, field.name, field.type(env_value))


def clean_rest_api_url(s: "Settings"):
    s.rest_api_url = s.rest_api_url.rstrip("/")


def clean_ws_api_url(s: "Settings"):
    s.ws_api_url = s.ws_api_url.rstrip("/")


@dataclass
class Settings:
    rest_api_url: str = "https://api-sandbox.idex.io/v1"
    ws_api_url: str = "wss://websocket-sandbox.idex.io/v1"
    eth_account_private_key: str = "0x3952043cbb4217a5cf45e6518f40bfce245c6d8b227039c4102ab8a09dd9dbd8"

    def __post_init__(self):
        inflect_env(self)
        clean_rest_api_url(self)
        clean_ws_api_url(self)


settings = Settings()

