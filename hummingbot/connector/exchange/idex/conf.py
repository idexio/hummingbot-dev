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

    # prod

    rest_api_url: str = "https://api.idex.io/v1"
    ws_api_url: str = "wss://websocket.idex.io/v1"

    # Sandbox
    # NOTE: You need to apply to get Sandbox API keys:
    # https://idex.io/#sandbox-signup

    # rest_api_url: str = "https://api-sandbox-eth.idex.io/v1"
    # ws_api_url: str = "wss://websocket-sandbox-eth.idex.io/v1"

    def __post_init__(self):
        inflect_env(self)
        clean_rest_api_url(self)
        clean_ws_api_url(self)


settings = Settings()
