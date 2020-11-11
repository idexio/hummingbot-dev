#!/usr/bin/env python

import os
from hummingbot.client.config.global_config_map import connector_keys

import logging as _logging
_logger = _logging.getLogger(__name__)

master_host = "***REMOVED***"
master_user = "***REMOVED***"
master_password = "***REMOVED***"
master_db = "***REMOVED***"

slave_host = "127.0.0.1"
slave_user = "reader"
slave_password = "falcon"
slave_db = "falcon"

mysql_master_server = "***REMOVED***"
mysql_slave_server = "***REMOVED***"

mysql_user = "***REMOVED***"
mysql_password = "***REMOVED***"
mysql_db = "***REMOVED***"

order_book_db = "***REMOVED***"
sparrow_db = "***REMOVED***"

order_books_db_2 = {
    "host": "***REMOVED***",
    "user": "***REMOVED***",
    "password": "***REMOVED***",
    "db": "**REMOVED***",
}

kafka_bootstrap_server = "***REMOVED***"

# whether to enable api mocking in unit test cases
mock_api_enabled = os.getenv("MOCK_API_ENABLED")

# ALL TEST KEYS
for key in connector_keys().keys():
    locals()[key] = os.getenv(key.upper())

"""
# Binance Tests
binance_api_key = os.getenv("BINANCE_API_KEY")
binance_api_secret = os.getenv("BINANCE_API_SECRET")

# Binance Perpetuals Tests
binance_perpetuals_api_key = os.getenv("BINANCE_PERPETUALS_API_KEY")
binance_perpetuals_api_secret = os.getenv("BINANCE_PERPETUALS_API_SECRET")

# Coinbase Pro Tests
coinbase_pro_api_key = os.getenv("COINBASE_PRO_API_KEY")
coinbase_pro_secret_key = os.getenv("COINBASE_PRO_SECRET_KEY")
coinbase_pro_passphrase = os.getenv("COINBASE_PRO_PASSPHRASE")


# Huobi Tests
huobi_api_key = os.getenv("HUOBI_API_KEY")
huobi_secret_key = os.getenv("HUOBI_SECRET_KEY")

# Dolomite Tests
dolomite_test_web3_private_key = os.getenv("DOLOMITE_TEST_PK")
dolomite_test_web3_address = os.getenv("DOLOMITE_TEST_ADDR")

# Loopring Tests
loopring_accountid = os.getenv("LOOPRING_ACCOUNTID")
loopring_exchangeid = os.getenv("LOOPRING_EXCHANGEID")
loopring_api_key = os.getenv("LOOPRING_API_KEY")
loopring_private_key = os.getenv("LOOPRING_PRIVATE_KEY")

# Bittrex Tests
bittrex_api_key = os.getenv("BITTREX_API_KEY")
bittrex_secret_key = os.getenv("BITTREX_SECRET_KEY")

# KuCoin Tests
kucoin_api_key = os.getenv("KUCOIN_API_KEY")
kucoin_secret_key = os.getenv("KUCOIN_SECRET_KEY")
kucoin_passphrase = os.getenv("KUCOIN_PASSPHRASE")

test_web3_provider_list = [os.getenv("WEB3_PROVIDER")]

# Liquid Tests
liquid_api_key = os.getenv("LIQUID_API_KEY")
liquid_secret_key = os.getenv("LIQUID_SECRET_KEY")

# Kraken Tests
kraken_api_key = os.getenv("KRAKEN_API_KEY")
kraken_secret_key = os.getenv("KRAKEN_SECRET_KEY")

# Eterbase Test
eterbase_api_key = os.getenv("ETERBASE_API_KEY")
eterbase_secret_key = os.getenv("ETERBASE_SECRET_KEY")
eterbase_account = os.getenv("ETERBASE_ACCOUNT")

# OKEx Test
okex_api_key = os.getenv("OKEX_API_KEY")
okex_secret_key = os.getenv("OKEX_SECRET_KEY")
okex_passphrase = os.getenv("OKEX_PASSPHRASE")

# CryptoCom Test
crypto_com_api_key = os.getenv("CRYPTO_COM_API_KEY")
crypto_com_secret_key = os.getenv("CRYPTO_COM_SECRET_KEY")

# Wallet Tests
test_erc20_token_address = os.getenv("TEST_ERC20_TOKEN_ADDRESS")
web3_test_private_key_a = os.getenv("TEST_WALLET_PRIVATE_KEY_A")
web3_test_private_key_b = os.getenv("TEST_WALLET_PRIVATE_KEY_B")
web3_test_private_key_c = os.getenv("TEST_WALLET_PRIVATE_KEY_C")

coinalpha_order_book_api_username = "***REMOVED***"
coinalpha_order_book_api_password = "***REMOVED***"
"""

kafka_2 = {
    "bootstrap_servers": "***REMOVED***",
    "zookeeper_servers": "***REMOVED***"
}


try:
    from .config_local import *             # noqa: F401, F403
except ModuleNotFoundError:
    pass

try:
    from .web3_wallet_secret import *       # noqa: F401, F403
except ModuleNotFoundError:
    pass

try:
    from .binance_secret import *           # noqa: F401, F403
except ModuleNotFoundError:
    pass

try:
    from .coinbase_pro_secrets import *     # noqa: F401, F403
except ModuleNotFoundError:
    pass
