import typing

from dataclasses import dataclass

from ..enums import *


@dataclass
class RestRequestCancelOrdersBase:
    nonce: str
    wallet: str


@dataclass
class RestRequestCancelOrder(RestRequestCancelOrdersBase):
    orderId: typing.Optional[str] = None
    market: typing.Optional[str] = None


@dataclass
class RestRequestCancelOrders(RestRequestCancelOrdersBase):
    """
    NOTE: This class is derived from JS lib and looks like useless
    """
    pass


RestRequestCancelOrderOrOrders = typing.Union[RestRequestCancelOrder, RestRequestCancelOrders]


@dataclass
class RestRequestCancelOrdersBody:
    parameters: RestRequestCancelOrderOrOrders
    signature: str


@dataclass
class RestRequestFindByWallet:
    nonce: str
    wallet: str


@dataclass
class RestRequestFindWithPagination:
    start: typing.Optional[int]
    end: typing.Optional[int]
    limit: typing.Optional[int]


class RestRequestFindBalances(RestRequestFindByWallet):
    asset: typing.Optional[str]


@dataclass
class RestRequestFindCandles(RestRequestFindWithPagination):
    market: str
    interval: CandleInterval


@dataclass
class RestRequestFindDeposit(RestRequestFindByWallet):
    depositId: str


@dataclass
class RestRequestFindDeposits(RestRequestFindByWallet, RestRequestFindWithPagination):
    asset: typing.Optional[str]
    fromId: typing.Optional[str]


@dataclass
class RestRequestFindFill(RestRequestFindByWallet):
    fillId: str


@dataclass
class RestRequestFindFills(RestRequestFindByWallet, RestRequestFindWithPagination):
    market: typing.Optional[str]
    fromId: typing.Optional[str]


@dataclass
class RestRequestFindMarkets:
    market: typing.Optional[str] = None
    regionOnly: typing.Optional[bool] = None


@dataclass
class RestRequestFindOrder(RestRequestFindByWallet):
    orderId: str


@dataclass
class RestRequestFindOrders(RestRequestFindByWallet, RestRequestFindWithPagination):
    market: typing.Optional[str]
    closed: typing.Optional[bool]
    fromId: typing.Optional[str]


@dataclass
class RestRequestFindTrades(RestRequestFindWithPagination):
    market: typing.Optional[str]
    fromId: typing.Optional[str]


@dataclass
class RestRequestFindWithdrawal(RestRequestFindByWallet):
    withdrawalId: str


@dataclass
class RestRequestFindWithdrawals(RestRequestFindByWallet, RestRequestFindWithPagination):
    asset: typing.Optional[str]
    assetContractAddress: typing.Optional[str]
    fromId: typing.Optional[str]


@dataclass
class RestRequestAllOrderParameters:
    """
    NOTE: Is not documented
    """
    nonce: str
    wallet: str
    market: str
    type: OrderType
    side: OrderSide
    timeInForce: typing.Optional[OrderTimeInForce]
    clientOrderId: typing.Optional[str]
    selfTradePrevention: typing.Optional[OrderSelfTradePrevention]
    cancelAfter: typing.Optional[typing.Union[int, float]]


@dataclass
class RestRequestLimitOrder(RestRequestAllOrderParameters):
    type: typing.Literal['limit', 'limitMaker']
    price: str


@dataclass
class RestRequestMarketOrder(RestRequestAllOrderParameters):
    type: typing.Literal['market']


@dataclass
class RestRequestStopLossOrder(RestRequestAllOrderParameters):
    type: typing.Literal['stopLoss']
    stopPrice: str


@dataclass
class RestRequestStopLossLimitOrder(RestRequestAllOrderParameters):
    type: typing.Literal['stopLossLimit']
    price: str
    stopPrice: str


@dataclass
class RestRequestTakeProfitOrder(RestRequestAllOrderParameters):
    type: typing.Literal['takeProfit']
    stopPrice: str


@dataclass
class RestRequestTakeProfitLimitOrder(RestRequestAllOrderParameters):
    type: typing.Literal['takeProfitLimit']
    price: str
    stopPrice: str


# TODO: Rethink accroding to python typehint spec
# @dataclass
# class RestRequestOrderByBaseQuantity(
#     typing.Union[
#         RestRequestLimitOrder,
#         RestRequestMarketOrder,
#         RestRequestStopLossOrder,
#         RestRequestStopLossLimitOrder,
#         RestRequestTakeProfitOrder,
#         RestRequestTakeProfitLimitOrder]):
#     quoteOrderQuantity: str
#     quantity: typing.Optional[int] = None


# TODO: Rethink accroding to python typehint spec
# @dataclass
# class RestRequestOrderByQuoteQuantity(
#     typing.Union[
#         RestRequestLimitOrder,
#         RestRequestMarketOrder,
#         RestRequestStopLossOrder,
#         RestRequestStopLossLimitOrder,
#         RestRequestTakeProfitOrder,
#         RestRequestTakeProfitLimitOrder]):
#     quoteOrderQuantity: str
#     quantity: typing.Optional[int] = None


RestRequestOrderWithPrice = typing.Union[
    RestRequestLimitOrder,
    RestRequestStopLossLimitOrder,
    RestRequestTakeProfitLimitOrder
]


RestRequestOrderWithStopPrice = typing.Union[
    RestRequestStopLossOrder,
    RestRequestStopLossLimitOrder,
    RestRequestTakeProfitLimitOrder,
    RestRequestTakeProfitLimitOrder
]


# TODO: Rethink accroding to python typehint spec
# RestRequestOrder = typing.Union[RestRequestOrderByBaseQuantity, RestRequestOrderByQuoteQuantity]


# TODO: Rethink accroding to python typehint spec
# @dataclass
# class RestRequestCreateOrderBody:
#     parameters: RestRequestOrder
#     signature: str


@dataclass
class RestRequestWithdrawalBase:
    nonce: str
    wallet: str
    quantity: str
    # Currently has no effect
    autoDispatchEnabled: typing.Optional[bool]


@dataclass
class RestRequestWithdrawalBySymbol(RestRequestWithdrawalBase):
    asset: str
    assetContractAddress: typing.Optional[str]


@dataclass
class RestRequestWithdrawalByAddress(RestRequestWithdrawalBase):
    assetContractAddress: str
    asset: typing.Optional[str]


RestRequestWithdrawal = typing.Union[RestRequestWithdrawalBySymbol, RestRequestWithdrawalByAddress]


@dataclass
class RestRequestCreateWithdrawalBody:
    parameters: RestRequestWithdrawal
    signature: str


@dataclass
class RestRequestAssociateWallet:
    nonce: str
    wallet: str


@dataclass
class RestRequestOrderBook:
    market: str
    level: typing.Optional[int] = None
    limit: typing.Optional[int] = None