import aiohttp
import asyncio
import logging
import statistics
import time
from collections import deque
from hummingbot.logger import HummingbotLogger
from hummingbot.core.utils.async_utils import safe_ensure_future


class BinanceTime:
    """
    Used to monkey patch Binance client's time module to adjust request timestamp when needed
    """
    BINANCE_TIME_API = "https://api.binance.com/api/v1/time"
    _bt_logger = None
    _bt_shared_instance = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._bt_logger is None:
            cls._bt_logger = logging.getLogger(__name__)
        return cls._bt_logger

    @classmethod
    def get_instance(cls) -> "BinanceTime":
        if cls._bt_shared_instance is None:
            cls._bt_shared_instance = BinanceTime()
        return cls._bt_shared_instance

    def __init__(self, check_interval: float = 60.0):
        self._time_offset_ms = deque([])
        self._set_server_time_offset_task = None
        self._started = False
        self.SERVER_TIME_OFFSET_CHECK_INTERVAL = check_interval
        self.median_window = 5
        # These 2 variables are used to prevent Binance time api getting called in too short interval (as triggered by
        # timestamp error from binance_market.pyx)
        self._last_time_offset_updated_ms = -100
        self._time_offset_update_min_interval_ms = 5000

    @property
    def started(self):
        return self._started

    def _get_time_offset_ms(self):
        if not self._time_offset_ms:
            return (time.time() - time.perf_counter()) * 1e3
        return statistics.median(self._time_offset_ms)

    def set_time_offset_ms(self, offset):
        self._time_offset_ms.append(offset)
        if len(self._time_offset_ms) > self.median_window:
            self._time_offset_ms.popleft()

    def time(self):
        return time.perf_counter() + self._get_time_offset_ms() * 1e-3

    def start(self):
        if self._set_server_time_offset_task is None:
            self._set_server_time_offset_task = safe_ensure_future(self.set_server_time_offset_loop())
            self._started = True

    def stop(self):
        if self._set_server_time_offset_task:
            self._set_server_time_offset_task.cancel()
            self._set_server_time_offset_task = None
            self._time_offset_ms.clear()
            self._started = False

    async def set_server_time_offset_loop(self):
        while True:
            await self.set_server_time_offset()
            await asyncio.sleep(self.SERVER_TIME_OFFSET_CHECK_INTERVAL)

    async def set_server_time_offset(self):
        try:
            time_start_ms = time.perf_counter() * 1e3
            if time_start_ms < self._last_time_offset_updated_ms + self._time_offset_update_min_interval_ms:
                return
            self._last_time_offset_updated_ms = time_start_ms
            async with aiohttp.ClientSession() as session:
                async with session.get(self.BINANCE_TIME_API) as resp:
                    resp_data = await resp.json()
                    binance_server_time = resp_data["serverTime"]
            time_end_ms = time.perf_counter() * 1e3
            expected_server_time = int((time_start_ms + time_end_ms) // 2)
            time_offset = binance_server_time - expected_server_time
            self.set_time_offset_ms(time_offset)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().network(f"Error getting Binance server time.", exc_info=True,
                                  app_warning_msg=f"Could not refresh Binance server time. "
                                                  f"Check network connection.\nException: {str(e)}")
