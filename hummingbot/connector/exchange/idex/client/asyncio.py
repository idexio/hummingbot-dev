import json
import typing
import functools

from dataclasses import dataclass, asdict
from urllib.parse import urlencode

from aiohttp import ClientSession, WSMsgType, WSMessage

from .exceptions import RemoteApiError
from ..conf import settings
from ..idex_auth import IdexAuth
from ..types.rest import request
from ..types.rest import response


def rest_decorator(call,
         request_cls: typing.Type = None,
         response_cls: typing.Type = None,
         method: str = "get",
         signed: bool = False):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(self, **kwargs):
            return await self.client.request(
                method,
                call,
                kwargs,
                request_cls=request_cls,
                response_cls=response_cls,
                signed=signed
            )
        return wrapper
    return decorator


class SignedRest:

    @staticmethod
    def get(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls, signed=True)

    @staticmethod
    def post(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls, "post", signed=True)

    @staticmethod
    def delete(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls, "delete", signed=True)


class Rest:

    @staticmethod
    def get(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls)

    @staticmethod
    def post(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls, "post")

    @staticmethod
    def delete(call: str, request_cls: typing.Type = None, response_cls: typing.Type = None):
        return rest_decorator(call, request_cls, response_cls, "delete")

    signed = SignedRest()


rest = Rest()


def clean_dict(data):
    if not isinstance(data, (dict, )):
        data = asdict(data)
    return {k: v for k, v in data.items() if v is not None}


def clean_locals(data):
    return {k: v for k, v in data.items() if k != "self"}


@dataclass
class AsyncBaseClient:

    session: ClientSession = None
    auth: IdexAuth = None

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
                      response_cls=None,
                      signed=False):
        if signed and not self.auth:
            raise Exception("IdexAuth instance required, auth attribute was not inited")

        if request_cls and isinstance(data, dict):
            data = request_cls(**data)

        # Init session
        url = f"{settings.rest_api_url}/{endpoint.lstrip('/')}"
        data = clean_dict(data) if data else None
        headers = {
            "Content-Type": "application/json"
        }
        body = None

        if signed:
            signed_payload = self.auth.generate_auth_dict(
                method,
                url,
                data if method == "get" else None,
                data if method != "get" else None
            )
            url = signed_payload["url"]
            headers = signed_payload["headers"]
            body = signed_payload.get("body")
        elif method == "get":
            url = f"{url}?{urlencode(data)}"
        else:
            body = json.dumps(data)

        # TODO: Move to logging
        print(f"{method.upper()}: {url} with {body}")
        async with self.session as session:
            resp = await session.request(
                method, url, headers=headers, body=body
            )
            if resp.status != 200:
                raise RemoteApiError(
                    code="RESPONSE_ERROR",
                    message=f"Got unexpected response with status `{resp.status}`"
                )
            result = await resp.json()
            # TODO: Move to logging
            # print(f"RESULT: {method.upper()}: {url} with {params or payload}\n {json.dumps(result, indent=2)}")
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
    trade: "Trade" = None

    def __post_init__(self):
        super(AsyncIdexClient, self).__post_init__()
        self.market = Market(client=self)
        self.public = Public(client=self)
        self.trade = Trade(client=self)


@dataclass()
class EndpointGroup:

    client: AsyncIdexClient


@dataclass
class Public(EndpointGroup):

    @rest.get("ping")
    async def get_ping(self) -> dict:
        pass

    @rest.get("time", response_cls=response.RestResponseTime)
    async def get_time(self) -> response.RestResponseTime:
        pass

    @rest.get("exchange", response_cls=response.RestResponseExchangeInfo)
    async def get_exchange(self) -> response.RestResponseExchangeInfo:
        pass

    @rest.get("assets", response_cls=response.RestResponseAsset)
    async def get_assets(self) -> typing.List[response.RestResponseAsset]:
        pass

    @rest.get("markets", response_cls=response.RestResponseMarket)
    async def get_markets(self) -> typing.List[response.RestResponseMarket]:
        pass


@dataclass
class Market(EndpointGroup):

    @rest.get("tickers", request.RestRequestFindMarkets, response.RestResponseTicker)
    async def get_tickers(self, *,
                          market: typing.Optional[str] = None,
                          regionOnly: typing.Optional[bool] = None) -> typing.List[response.RestResponseTicker]:
        pass

    @rest.get("candles", request.RestRequestFindCandles, response.RestResponseCandle)
    async def get_candles(self, *,
                          market: str,
                          interval: request.CandleInterval,
                          start: typing.Optional[int] = None,
                          end: typing.Optional[int] = None,
                          limit: typing.Optional[int] = None) -> typing.List[response.RestResponseCandle]:
        pass

    @rest.get("trades", request.RestRequestFindTrades, response.RestResponseTrade)
    async def get_trades(self, *,
                         market: str,
                         start: typing.Optional[int] = None,
                         end: typing.Optional[int] = None,
                         limit: typing.Optional[int] = None,
                         fromId: typing.Optional[str] = None) -> typing.List[response.RestResponseTrade]:
        pass

    @rest.get("orderbook", request.RestRequestOrderBook, response.RestResponseOrderBook)
    async def get_orderbook(self, *,
                            market: str,
                            level: typing.Optional[int] = 1,
                            limit: typing.Optional[int] = 50) -> response.RestResponseOrderBook:
        pass


@dataclass
class Trade(EndpointGroup):

    @rest.signed.post("orders", request.RestRequestCreateOrderBody, response.RestResponseOrder)
    async def create_order(self,
                           parameters: request.RestRequestOrder) -> response.RestResponseOrder:
        pass

    @rest.signed.delete("orders", request.RestRequestCancelOrdersBody, response.RestResponseCanceledOrderItem)
    async def cancel_order(self,
                           parameters: request.RestRequestCancelOrder) -> response.RestResponseCanceledOrder:
        pass
