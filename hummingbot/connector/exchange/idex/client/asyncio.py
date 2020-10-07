import typing

from dataclasses import dataclass, asdict
from aiohttp import ClientSession, WSMsgType, WSMessage

from .exceptions import RemoteApiError
from ..conf import settings
from ..types.rest import request
from ..types.rest import response


def clean_dict(data):
    if not isinstance(data, (dict, )):
        data = asdict(data)
    return {k: v for k, v in data.items() if v is not None}


def clean_locals(data):
    return {k: v for k, v in data.items() if k != "self"}


@dataclass
class AsyncBaseClient:

    session: ClientSession = None

    def __post_init__(self):
        if not self.session:
            self.session = ClientSession()

    async def subscribe(self,
                        subscriptions: typing.List[typing.Union[str, typing.Dict]] = None,
                        markets: typing.List[str] = None,
                        method: str = "subscribe",
                        message_cls: typing.Type = None):
        url = settings.ws_api_url
        async with self.session.ws_connect(url) as ws:
            subscription_request = {
                "method": method,
            }
            if markets:
                subscription_request.update({
                    "markets": markets
                })
            if subscriptions:
                subscription_request.update({
                    "subscriptions": subscriptions
                })

            await ws.send_json(subscription_request)
            async for message in ws:   # type: WSMessage
                if message.type in (
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSED,
                        WSMsgType.CLOSING,
                        WSMsgType.ERROR):
                    break
                message = message.json()
                if message_cls and isinstance(message, dict):
                    message = message_cls(**message)
                yield message

        # async with websockets.connect(stream_url) as ws:
        #     ws: websockets.WebSocketClientProtocol = ws
        #     async for raw_msg in self._inner_messages(ws):
        #         msg = ujson.loads(raw_msg)
        #         trade_msg: OrderBookMessage = BinanceOrderBook.trade_message_from_exchange(msg)
        #         output.put_nowait(trade_msg)

    async def request(self,
                      method: str,
                      endpoint: str,
                      data: typing.Union[dict, typing.Any] = None,
                      request_cls=None,
                      response_cls=None):
        if request_cls and isinstance(data, dict):
            data = request_cls(**data)

        params = None
        payload = None
        if method == "get":
            # Clean params
            params = clean_dict(data) if data else None
        else:
            # Clean payload
            payload = clean_dict(data) if data else None

        # Init sesssion
        abs_endpoint = f"{settings.rest_api_url}/{endpoint.lstrip('/')}"

        # TODO: Move to logging
        print(f"{method.upper()}: {abs_endpoint} with {params or payload}")

        async with self.session as session:
            resp = await session.request(
                method, abs_endpoint, params=params, json=payload
            )
            if resp.status != 200:
                raise RemoteApiError(
                    code="RESPONSE_ERROR",
                    message=f"Got unexpected response with status `{resp.status}`"
                )
            result = await resp.json()
            if isinstance(result, dict) and set(result.keys()) == {"code", "message"}:
                raise RemoteApiError(
                    code=result["code"],
                    message=result["message"]
                )
            if response_cls and isinstance(result, list):
                return [response_cls(**obj) for obj in result]
            elif response_cls and isinstance(result, dict):
                return response_cls(**result)
            else:
                return result


class AsyncIdexClient(AsyncBaseClient):

    market: "Market" = None
    public: "Public" = None

    def __post_init__(self):
        super(AsyncIdexClient, self).__post_init__()
        self.market = Market(client=self)
        self.public = Public(client=self)


@dataclass
class Public:

    client: AsyncIdexClient

    async def get_ping(self) -> dict:
        return await self.client.request("get", "ping")

    async def get_time(self) -> response.RestResponseTime:
        return await self.client.request(
            "get", "time",
            response_cls=response.RestResponseTime
        )

    async def get_exchange(self) -> response.RestResponseExchangeInfo:
        return await self.client.request(
            "get", "exchange",
            response_cls=response.RestResponseExchangeInfo
        )

    async def get_assets(self) -> typing.List[response.RestResponseAsset]:
        return await self.client.request(
            "get", "assets",
            response_cls=response.RestResponseAsset
        )

    async def get_markets(self) -> typing.List[response.RestResponseMarket]:
        return await self.client.request(
            "get", "markets",
            response_cls=response.RestResponseMarket
        )


@dataclass
class Market:

    client: AsyncIdexClient

    async def get_tickers(self,
                          market: typing.Optional[str] = None,
                          regionOnly: typing.Optional[bool] = None) -> typing.List[response.RestResponseTicker]:
        return await self.client.request(
            "get", "tickers", clean_locals(locals()),
            request_cls=request.RestRequestFindMarkets,
            response_cls=response.RestResponseTicker
        )

    async def get_candles(self,
                          market: str,
                          interval: request.CandleInterval,
                          start: typing.Optional[int] = None,
                          end: typing.Optional[int] = None,
                          limit: typing.Optional[int] = None) -> typing.List[response.RestResponseCandle]:
        return await self.client.request(
            "get", "candles", clean_locals(locals()),
            request_cls=request.RestRequestFindCandles,
            response_cls=response.RestResponseCandle
        )

    async def get_trades(self,
                         market: str,
                         start: typing.Optional[int] = None,
                         end: typing.Optional[int] = None,
                         limit: typing.Optional[int] = None,
                         fromId: typing.Optional[str] = None) -> typing.List[response.RestResponseTrade]:
        return await self.client.request(
            "get", "trades", clean_locals(locals()),
            request_cls=request.RestRequestFindTrades,
            response_cls=response.RestResponseTrade
        )

    async def get_orderbook(self,
                            market: str,
                            level: typing.Optional[int] = 1,
                            limit: typing.Optional[int] = 50) -> response.RestResponseOrderBook:
        return await self.client.request(
            "get", "orderbook", clean_locals(locals()),
            request_cls=request.RestRequestOrderBook,
            response_cls=response.RestResponseOrderBook
        )
