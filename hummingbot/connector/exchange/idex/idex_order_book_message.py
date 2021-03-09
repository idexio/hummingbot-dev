import pandas as pd
from typing import (
    Dict,
    List,
    Optional,
)

from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.core.data_type.order_book_message import (
    OrderBookMessage,
    OrderBookMessageType,
)


class IdexOrderBookMessage(OrderBookMessage):
    def __new__(
        cls,
        message_type: OrderBookMessageType,
        content: Dict[str, any],
        timestamp: Optional[float] = None,
        *args,
        **kwargs,
    ):
        if timestamp is None:
            if message_type is OrderBookMessageType.SNAPSHOT:
                raise ValueError("timestamp must not be None when initializing snapshot messages.")
            timestamp = pd.Timestamp(content["data"]["t"], unit="ms", tz="UTC").timestamp()
        return super(IdexOrderBookMessage, cls).__new__(
            cls, message_type, content, timestamp=timestamp, *args, **kwargs
        )

    @property
    def update_id(self) -> int:
        if self.type in [OrderBookMessageType.DIFF, OrderBookMessageType.SNAPSHOT]:
            # TODO: ALF: self.content["sequence"]  (coinbase)   or  self.timestamp * 1e3  (crypto.com)  ???
            return int(self.content["sequence"])
        else:
            return -1

    @property
    def trade_id(self) -> int:
        if self.type is OrderBookMessageType.TRADE:
            return int(self.content["sequence"])
        return -1

    @property
    def trading_pair(self) -> str:
        # TODO ALF: check 'product_id' and 'symbol' are present
        if "product_id" in self.content:
            return self.content["product_id"]
        elif "symbol" in self.content:
            return self.content["symbol"]

    @property
    def asks(self) -> List[OrderBookRow]:
        raise NotImplementedError("Idex order book messages have different semantics.")

    @property
    def bids(self) -> List[OrderBookRow]:
        raise NotImplementedError("Idex order book messages have different semantics.")
