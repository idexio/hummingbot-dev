import re

from typing import Optional

from .client.sync import SyncIdexClient


ASSETS = [asset.symbol for asset in SyncIdexClient().public.get_assets()]
TRADING_PAIR_SPLITTER = re.compile(rf"^(\w+)({'|'.join(ASSETS)})$")


def to_idex_pair(pair: str) -> Optional[str]:
    try:
        m = TRADING_PAIR_SPLITTER.match(pair)
        return f"{m.group(1)}-{m.group(2)}"
    # TODO: What the ... is that below?
    # Exceptions are now logged as warnings in trading pair fetcher
    except Exception:
        return None
