from typing import Optional

from hummingbot.client.config.config_validators import validate_bool
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_methods import using_exchange
from hummingbot.client.config.global_config_map import global_config_map


CENTRALIZED = False

USE_ETHEREUM_WALLET = False

EXAMPLE_PAIR = "IDEX-ETH"

DEFAULT_FEES = [0.1, 0.2]


EXCHANGE_NAME = "idex"

IDEX_BLOCKCHAINS = ('ETH', 'BSC')

# API Feed adjusted to sandbox url
IDEX_REST_URL_FMT = "https://api-sandbox-{blockchain}.idex.io/"
# WS Feed adjusted to sandbox url
IDEX_WS_FEED_FMT = "wss://websocket-sandbox-{blockchain}.idex.io/v1"


_IDEX_REST_URL_SANDBOX_ETH = "https://api-sandbox-eth.idex.io"
_IDEX_REST_URL_SANDBOX_BSC = "https://api-sandbox-bsc.idex.io"
_IDEX_REST_URL_PROD_ETH = "https://api-eth.idex.io"
_IDEX_REST_URL_PROD_BSC = "https://api-bsc.idex.io"

_IDEX_WS_FEED_SANDBOX_ETH = "wss://websocket-sandbox-eth.idex.io/v1"
_IDEX_WS_FEED_SANDBOX_BSC = "wss://websocket-sandbox-bsc.idex.io/v1"
_IDEX_WS_FEED_PROD_ETH = "wss://websocket-eth.idex.io/v1"
_IDEX_WS_FEED_PROD_BSC = "wss://websocket-bsc.idex.io/v1"


# late resolution to give time for exchange configuration to be ready
_IDEX_REST_URL = None
_IDEX_WS_FEED = None


def get_idex_rest_url():
    global _IDEX_REST_URL
    if not _IDEX_REST_URL:
        sandbox_str = global_config_map["idex_use_sandbox"].value
        use_sandbox = True if sandbox_str in ('true', 'yes', 'y') else False
        blockchain = global_config_map["idex_contract_blockchain"].value
        if use_sandbox:
            _IDEX_REST_URL = _IDEX_REST_URL_SANDBOX_ETH if blockchain == 'ETH' else _IDEX_REST_URL_SANDBOX_BSC
        else:
            _IDEX_REST_URL = _IDEX_REST_URL_PROD_ETH if blockchain == 'ETH' else _IDEX_REST_URL_PROD_BSC
    return _IDEX_REST_URL


def get_idex_ws_feed():
    global _IDEX_WS_FEED
    if not _IDEX_WS_FEED:
        sandbox_str = global_config_map["idex_use_sandbox"].value
        use_sandbox = True if sandbox_str in ('true', 'yes', 'y') else False
        blockchain = global_config_map["idex_contract_blockchain"].value
        if use_sandbox:
            _IDEX_WS_FEED = _IDEX_WS_FEED_SANDBOX_ETH if blockchain == 'ETH' else _IDEX_WS_FEED_SANDBOX_BSC
        else:
            _IDEX_WS_FEED = _IDEX_WS_FEED_PROD_ETH if blockchain == 'ETH' else _IDEX_WS_FEED_PROD_BSC
    return _IDEX_WS_FEED

def validate_idex_contract_blockchain(value: str) -> Optional[str]:
    if value not in IDEX_BLOCKCHAINS:
        return f'Value {value} must be one of: {IDEX_BLOCKCHAINS}'

KEYS = {
    "idex_api_key":
        ConfigVar(key="idex_api_key",
                  prompt="Enter your IDEX API key >>> ",
                  required_if=using_exchange(EXCHANGE_NAME),
                  is_secure=True,
                  is_connect_key=True),
    "idex_api_secret_key":
        ConfigVar(key="idex_api_secret_key",
                  prompt="Enter your IDEX API secret key>>> ",
                  required_if=using_exchange(EXCHANGE_NAME),
                  is_secure=True,
                  is_connect_key=True),
    "idex_wallet_private_key":
        ConfigVar(key="idex_wallet_private_key",
                  prompt="Enter your wallet private key>>> ",
                  required_if=using_exchange(EXCHANGE_NAME),
                  is_secure=True,
                  is_connect_key=True),
    "idex_contract_blockchain":
        ConfigVar(key="idex_contract_blockchain",
                  prompt=f"Enter blockchain to interact with IDEX contract ({'/'.join(IDEX_BLOCKCHAINS)})>>> ",
                  required_if=using_exchange(EXCHANGE_NAME),
                  default='ETH',
                  validator=validate_idex_contract_blockchain,
                  is_secure=True,
                  is_connect_key=False),
    "idex_use_sandbox":
        ConfigVar(key="idex_use_sandbox",
                  prompt="Trade in IDEX sandbox environment for testing purposes? (no/yes)>>> ",
                  required_if=using_exchange(EXCHANGE_NAME),
                  default='no',
                  validator=validate_bool,
                  is_secure=True,
                  is_connect_key=False),
}
