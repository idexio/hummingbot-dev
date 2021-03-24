#!/usr/bin/env python
from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../../")))
import asyncio
import logging
import unittest

from hummingbot.connector.exchange.idex.idex_user_stream_tracker import IdexUserStreamTracker
from hummingbot.connector.exchange.idex.idex_auth import IdexAuth
from hummingbot.core.utils.async_utils import safe_ensure_future


class IdexUserStreamTrackerUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        IDEX_API_KEY = "889fe7dd-ea60-4bf4-86f8-4eec39146510"
        IDEX_SECRET_KEY = "tkDey53dr1ZlyM2tzUAu82l+nhgzxCJl"
        IDEX_PRIVATE_KEY = "0227070369c04f55c66988ee3b272f8ae297cf7967ca7bad6d2f71f72072e18d"  # don't commit me please

        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.idex_auth = IdexAuth(IDEX_API_KEY, IDEX_SECRET_KEY, IDEX_PRIVATE_KEY)

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
