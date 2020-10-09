import functools
import json
import typing

from dataclasses import dataclass, asdict
from aiohttp import ClientSession, WSMsgType, WSMessage

from .exceptions import RemoteApiError
from ..conf import settings
from ..types.rest import request
from ..types.rest import response


def rest(call, request_cls=None, response_cls=None, method="get"):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(self, **kwargs):
            return await self.client.request(
                method,
                call,
                kwargs,
                request_cls=request_cls,
                response_cls=response_cls
            )
        return wrapper
    return decorator


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

        # Init session
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
            # TODO: Move to logging
            print(f"RESULT: {method.upper()}: {abs_endpoint} with {params or payload}\n {json.dumps(result, indent=2)}")
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

    @rest("ping")
    async def get_ping(self) -> dict:
        pass

    @rest("time", response_cls=response.RestResponseTime)
    async def get_time(self) -> response.RestResponseTime:
        pass

    @rest("exchange", response_cls=response.RestResponseExchangeInfo)
    async def get_exchange(self) -> response.RestResponseExchangeInfo:
        pass

    @rest("assets", response_cls=response.RestResponseAsset)
    async def get_assets(self) -> typing.List[response.RestResponseAsset]:
        pass

    @rest("markets", response_cls=response.RestResponseMarket)
    async def get_markets(self) -> typing.List[response.RestResponseMarket]:
        pass


@dataclass
class Market:

    client: AsyncIdexClient

    @rest("tickers", request.RestRequestFindMarkets, response.RestResponseTicker)
    async def get_tickers(self, *,
                          market: typing.Optional[str] = None,
                          regionOnly: typing.Optional[bool] = None) -> typing.List[response.RestResponseTicker]:
        pass

    @rest("candles", request.RestRequestFindCandles, response.RestResponseCandle)
    async def get_candles(self, *,
                          market: str,
                          interval: request.CandleInterval,
                          start: typing.Optional[int] = None,
                          end: typing.Optional[int] = None,
                          limit: typing.Optional[int] = None) -> typing.List[response.RestResponseCandle]:
        pass

    @rest("trades", request.RestRequestFindTrades, response.RestResponseTrade)
    async def get_trades(self, *,
                         market: str,
                         start: typing.Optional[int] = None,
                         end: typing.Optional[int] = None,
                         limit: typing.Optional[int] = None,
                         fromId: typing.Optional[str] = None) -> typing.List[response.RestResponseTrade]:
        pass

    @rest("orderbook", request.RestRequestOrderBook, response.RestResponseOrderBook)
    async def get_orderbook(self, *,
                            market: str,
                            level: typing.Optional[int] = 1,
                            limit: typing.Optional[int] = 50) -> response.RestResponseOrderBook:
        pass
