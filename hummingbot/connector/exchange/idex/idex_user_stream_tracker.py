import asyncio
import logging

from typing import Optional, List

from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.user_stream_tracker import UserStreamTracker
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather


from hummingbot.connector.exchange.idex.idex_api_user_stream_data_source import IdexAPIUserStreamDataSource
from hummingbot.connector.exchange.idex.idex_auth import IdexAuth


class IdexUserStreamTracker(UserStreamTracker):
    _idex_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        cls._idex_logger = cls._idex_logger or logging.getLogger(__name__)
        return cls._idex_logger

    def __init__(self,
                 idex_auth: Optional[IdexAuth] = None,
                 trading_pairs: Optional[List[str]] = [],
                 domain: str = "eth"):
        super(IdexUserStreamTracker, self).__init__()
        self._idex_auth: IdexAuth = idex_auth
        self._trading_pairs: List[str] = trading_pairs
        self._ev_loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()
        self._data_source: Optional[UserStreamTrackerDataSource] = None
        self._user_stream_tracking_task: Optional[asyncio.Task] = None
        self._domain = domain

    @property
    def data_source(self) -> UserStreamTrackerDataSource:
        if not self._data_source:
            self._data_source = IdexAPIUserStreamDataSource(
                idex_auth=self._idex_auth,
                trading_pairs=self._trading_pairs,
                domain=self._domain
            )
        return self._data_source

    @property
    def exchange_name(self) -> str:
        if self._domain == "eth":  # prod with ETH blockchain
            return "idex"
        else:
            return f"idex_{self._domain}"

    async def start(self):
        self._user_stream_tracking_task = safe_ensure_future(
            self.data_source.listen_for_user_stream(self._ev_loop, self._user_stream)
        )
        await safe_gather(self._user_stream_tracking_task)
