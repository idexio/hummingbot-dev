#!/usr/bin/env python
from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../../")))
import asyncio
import logging
import unittest
import conf

from hummingbot.connector.exchange.idex.idex_user_stream_tracker import IdexUserStreamTracker
from hummingbot.connector.exchange.idex.idex_auth import IdexAuth
from hummingbot.core.utils.async_utils import safe_ensure_future


# API_SECRET length must be multiple of 4 otherwise base64.b64decode will fail
API_MOCK_ENABLED = conf.mock_api_enabled is not None and conf.mock_api_enabled.lower() in ['true', 'yes', '1']

# load config from Hummingbot's central debug conf
# Values can be overridden by env variables (in uppercase). Example: export IDEX_WALLET_PRIVATE_KEY="1234567"
IDEX_API_KEY = getattr(conf, 'idex_api_key') or ''
IDEX_API_SECRET_KEY = getattr(conf, 'idex_api_secret_key') or ''
IDEX_WALLET_PRIVATE_KEY = getattr(conf, 'idex_wallet_private_key') or ''
IDEX_CONTRACT_BLOCKCHAIN = getattr(conf, 'idex_contract_blockchain') or 'ETH'
IDEX_USE_SANDBOX = True if getattr(conf, 'idex_use_sandbox') is None else getattr(conf, 'idex_use_sandbox')

# force resolution of api base url for conf values provided to this test
# hummingbot.connector.exchange.idex.idex_resolve._IS_IDEX_SANDBOX = IDEX_USE_SANDBOX
# hummingbot.connector.exchange.idex.idex_resolve._IDEX_BLOCKCHAIN = IDEX_CONTRACT_BLOCKCHAIN


class IdexUserStreamTrackerUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        idex_api_key = IDEX_API_KEY
        idex_secret_key = IDEX_API_SECRET_KEY
        idex_wallet_private_key = IDEX_WALLET_PRIVATE_KEY

        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.idex_auth = IdexAuth(idex_api_key, idex_secret_key, idex_wallet_private_key)

        cls.user_stream_tracker: IdexUserStreamTracker = IdexUserStreamTracker(idex_auth=cls.idex_auth, trading_pairs=['DIL-ETH'])
        cls.user_stream_tracker_task: asyncio.Task = safe_ensure_future(cls.user_stream_tracker.start())

    def run_async(self, task):
        return self.ev_loop.run_until_complete(task)

    def test_user_stream(self):
        self.ev_loop.run_until_complete(asyncio.sleep(20.0))
        print(self.user_stream_tracker.user_stream)


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
