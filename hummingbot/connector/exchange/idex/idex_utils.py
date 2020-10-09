from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_methods import using_exchange


CENTRALIZED = True

EXAMPLE_PAIR = "DIL-ETH"

DEFAULT_FEES = [0.1, 0.2]

KEYS = {
    "idex_api_key":
        ConfigVar(key="idex_api_key",
                  prompt="Enter your IDEX API key >>> ",
                  required_if=using_exchange("idex"),
                  is_secure=True,
                  is_connect_key=True),
    "idex_api_secret":
        ConfigVar(key="idex_api_secret",
                  prompt="Enter your IDEX API secret >>> ",
                  required_if=using_exchange("idex"),
                  is_secure=True,
                  is_connect_key=True),
}
