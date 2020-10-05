import typing

from dataclasses import dataclass, asdict
from requests import Session

from .exceptions import RemoteApiError
from ..conf import settings
from ..types.rest import response


def clean_dict(data):
    if not isinstance(data, (dict, )):
        data = asdict(data)
    return {k: v for k, v in data.items() if v is not None}


def clean_locals(data):
    return {k: v for k, v in data.items() if k != "self"}


@dataclass
class SyncBaseClient:

    session: Session = None

    def __post_init__(self):
        if not self.session:
            self.session = Session()

    def request(self,
                method: str,
                endpoint: str,
                request: typing.Union[dict, typing.Any] = None):
        params = None
        payload = None
        if method == "get":
            # Clean params
            params = clean_dict(request) if request else None
        else:
            # Clean payload
            payload = clean_dict(request) if request else None

        # Init sesssion
        abs_endpoint = f"{settings.rest_api_url}/{endpoint.lstrip('/')}"

        # TODO: Move to logging
        print(f"{method.upper()}: {abs_endpoint} with {params or payload}")

        with self.session as session:
            result = session.request(
                method,
                abs_endpoint,
                params=params,
                json=payload
            ).json()
            if isinstance(result, dict) and set(result.keys()) == {"code", "message"}:
                raise RemoteApiError(
                    code=result["code"],
                    message=result["message"]
                )
            return result


class SyncIdexClient(SyncBaseClient):

    public: "Public" = None

    def __post_init__(self):
        super(SyncIdexClient, self).__post_init__()
        self.public = Public(client=self)


@dataclass
class Public:

    client: SyncIdexClient

    def get_ping(self) -> dict:
        return self.client.request("get", "ping")

    def get_time(self) -> response.RestResponseTime:
        return response.RestResponseTime(**(
            self.client.request("get", "time")
        ))

    def get_exchange(self) -> response.RestResponseExchangeInfo:
        return response.RestResponseExchangeInfo(**(
            self.client.request("get", "exchange")
        ))

    def get_assets(self) -> typing.List[response.RestResponseAsset]:
        return [response.RestResponseAsset(**obj) for obj in (
            self.client.request("get", "assets")
        )]

    def get_markets(self) -> typing.List[response.RestResponseMarket]:
        return [response.RestResponseMarket(**obj) for obj in (
            self.client.request("get", "markets")
        )]
