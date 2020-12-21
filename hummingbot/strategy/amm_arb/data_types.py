from decimal import Decimal
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.core.utils.estimate_fee import estimate_fee

s_decimal_nan = Decimal("NaN")
s_decimal_0 = Decimal("0")


class ArbProposalSide:
    """
    An arbitrage proposal side which contains info needed for order submission.
    """
    def __init__(self,
                 market_info: MarketTradingPairTuple,
                 is_buy: bool,
                 quote_price: Decimal,
                 order_price: Decimal,
                 amount: Decimal
                 ):
        """
        :param market_info: The market where to submit the order
        :param is_buy: True if buy order
        :param quote_price: The quote price (for an order amount) from the market
        :param order_price: The price required for order submission, this could differ from the quote price
        :param amount: The order amount
        """
        self.market_info: MarketTradingPairTuple = market_info
        self.is_buy: bool = is_buy
        self.quote_price: Decimal = quote_price
        self.order_price: Decimal = order_price
        self.amount: Decimal = amount

    def __repr__(self):
        side = "buy" if self.is_buy else "sell"
        return f"Connector: {self.market_info.market.display_name}  Side: {side}  Quote Price: {self.quote_price}  " \
               f"Order Price: {self.order_price}  Amount: {self.amount}"


class ArbProposal:
    """
    An arbitrage proposal which contains 2 sides of the proposal - one buy and one sell.
    """
    def __init__(self, first_side: ArbProposalSide, second_side: ArbProposalSide):
        if first_side.is_buy == second_side.is_buy:
            raise Exception("first_side and second_side must be on different side of buy and sell.")
        self.first_side: ArbProposalSide = first_side
        self.second_side: ArbProposalSide = second_side

    def profit_pct(self, account_for_fee: bool = False, first_side_quote_eth_rate: Decimal = None,
                   second_side_quote_eth_rate: Decimal = None) -> Decimal:
        """
        Returns a profit in percentage value (e.g. 0.01 for 1% profitability)
        """
        buy = self.first_side if self.first_side.is_buy else self.second_side
        sell = self.first_side if not self.first_side.is_buy else self.second_side
        if buy.quote_price == 0:
            return s_decimal_0
        if not account_for_fee:
            return (sell.quote_price - buy.quote_price) / buy.quote_price
        buy_trade_fee = estimate_fee(buy.market_info.market.name, False)
        sell_trade_fee = estimate_fee(sell.market_info.market.name, False)
        buy_quote_eth_rate = first_side_quote_eth_rate if self.first_side.is_buy else second_side_quote_eth_rate
        sell_quote_eth_rate = first_side_quote_eth_rate if not self.first_side.is_buy else second_side_quote_eth_rate
        if buy_quote_eth_rate is not None and buy_trade_fee.flat_fees[0][0].upper() == "ETH":
            buy_fee_amount = buy_trade_fee.flat_fees[0][1] / buy_quote_eth_rate
        else:
            buy_fee_amount = buy_trade_fee.fee_amount_in_quote(buy.market_info.trading_pair,
                                                               buy.quote_price, buy.amount)
        if sell_quote_eth_rate is not None and sell_trade_fee.flat_fees[0][0].upper() == "ETH":
            sell_fee_amount = sell_trade_fee.flat_fees[0][1] / sell_quote_eth_rate
        else:
            sell_fee_amount = sell_trade_fee.fee_amount_in_quote(sell.market_info.trading_pair, sell.quote_price,
                                                                 sell.amount)

        # buy_fee_amount = buy_trade_fee.fee_amount_in_quote(buy.market_info.trading_pair,
        #                                                    buy.quote_price, buy.amount)
        # sell_fee_amount = sell_trade_fee.fee_amount_in_quote(sell.market_info.trading_pair, sell.quote_price,
        #                                                      sell.amount)

        sell_gained_net = (sell.amount * sell.quote_price) - sell_fee_amount
        buy_spent_net = (buy.amount * buy.quote_price) + buy_fee_amount
        return ((sell_gained_net - buy_spent_net) / buy_spent_net) if buy_spent_net != s_decimal_0 else s_decimal_0

    def __repr__(self):
        return f"First Side - {self.first_side}\nSecond Side - {self.second_side}"

    def copy(self):
        return ArbProposal(ArbProposalSide(self.first_side.market_info, self.first_side.is_buy,
                                           self.first_side.quote_price, self.first_side.order_price,
                                           self.first_side.amount),
                           ArbProposalSide(self.second_side.market_info, self.second_side.is_buy,
                                           self.second_side.quote_price, self.second_side.order_price,
                                           self.second_side.amount))
