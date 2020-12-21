from decimal import Decimal
import logging
import pandas as pd
from typing import (
    List)

from hummingbot.core.clock cimport Clock
from hummingbot.core.event.events import MarketEvent
from hummingbot.core.event.event_listener cimport EventListener
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.core.time_iterator cimport TimeIterator
from hummingbot.connector.connector_base cimport ConnectorBase
from hummingbot.core.data_type.trade import Trade
from hummingbot.core.event.events import (
    OrderFilledEvent,
    OrderType,
    PositionAction
)

from .order_tracker import OrderTracker

NaN = float("nan")
s_decimal_nan = Decimal("NaN")
s_decimal_0 = Decimal("0")

# <editor-fold desc="+ Event listeners">
cdef class BaseStrategyEventListener(EventListener):
    cdef:
        StrategyBase _owner

    def __init__(self, StrategyBase owner):
        super().__init__()
        self._owner = owner


cdef class BuyOrderCompletedListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_complete_buy_order(arg)
        self._owner.c_did_complete_buy_order_tracker(arg)


cdef class SellOrderCompletedListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_complete_sell_order(arg)
        self._owner.c_did_complete_sell_order_tracker(arg)


cdef class OrderFilledListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_fill_order(arg)


cdef class OrderFailedListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_fail_order(arg)
        self._owner.c_did_fail_order_tracker(arg)


cdef class OrderCancelledListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_cancel_order(arg)
        self._owner.c_did_cancel_order_tracker(arg)


cdef class OrderExpiredListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_expire_order(arg)
        self._owner.c_did_expire_order_tracker(arg)


cdef class BuyOrderCreatedListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_create_buy_order(arg)


cdef class SellOrderCreatedListener(BaseStrategyEventListener):
    cdef c_call(self, object arg):
        self._owner.c_did_create_sell_order(arg)
# </editor-fold>


cdef class StrategyBase(TimeIterator):
    BUY_ORDER_COMPLETED_EVENT_TAG = MarketEvent.BuyOrderCompleted.value
    SELL_ORDER_COMPLETED_EVENT_TAG = MarketEvent.SellOrderCompleted.value
    ORDER_FILLED_EVENT_TAG = MarketEvent.OrderFilled.value
    ORDER_CANCELLED_EVENT_TAG = MarketEvent.OrderCancelled.value
    ORDER_EXPIRED_EVENT_TAG = MarketEvent.OrderExpired.value
    ORDER_FAILURE_EVENT_TAG = MarketEvent.OrderFailure.value
    BUY_ORDER_CREATED_EVENT_TAG = MarketEvent.BuyOrderCreated.value
    SELL_ORDER_CREATED_EVENT_TAG = MarketEvent.SellOrderCreated.value

    @classmethod
    def logger(cls) -> logging.Logger:
        raise NotImplementedError

    def __init__(self):
        super().__init__()
        self._sb_markets = set()
        self._sb_create_buy_order_listener = BuyOrderCreatedListener(self)
        self._sb_create_sell_order_listener = SellOrderCreatedListener(self)
        self._sb_fill_order_listener = OrderFilledListener(self)
        self._sb_fail_order_listener = OrderFailedListener(self)
        self._sb_cancel_order_listener = OrderCancelledListener(self)
        self._sb_expire_order_listener = OrderExpiredListener(self)
        self._sb_complete_buy_order_listener = BuyOrderCompletedListener(self)
        self._sb_complete_sell_order_listener = SellOrderCompletedListener(self)

        self._sb_delegate_lock = False

        self._sb_order_tracker = OrderTracker()

    @property
    def active_markets(self) -> List[ConnectorBase]:
        return list(self._sb_markets)

    def format_status(self):
        raise NotImplementedError

    def log_with_clock(self, log_level: int, msg: str, **kwargs):
        clock_timestamp = pd.Timestamp(self._current_timestamp, unit="s", tz="UTC")
        self.logger().log(log_level, f"{msg} [clock={str(clock_timestamp)}]", **kwargs)

    @property
    def trades(self) -> List[Trade]:
        def event_to_trade(order_filled_event: OrderFilledEvent, market_name: str):
            return Trade(order_filled_event.trading_pair,
                         order_filled_event.trade_type,
                         order_filled_event.price,
                         order_filled_event.amount,
                         order_filled_event.order_type,
                         market_name,
                         order_filled_event.timestamp,
                         order_filled_event.trade_fee)
        past_trades = []
        for market in self.active_markets:
            event_logs = market.event_logs
            order_filled_events = list(filter(lambda e: isinstance(e, OrderFilledEvent), event_logs))
            past_trades += list(map(lambda ofe: event_to_trade(ofe, market.display_name), order_filled_events))

        return sorted(past_trades, key=lambda x: x.timestamp)

    def market_status_data_frame(self, market_trading_pair_tuples: List[MarketTradingPairTuple]) -> pd.DataFrame:
        cdef:
            ConnectorBase market
            str trading_pair
            str base_asset
            str quote_asset
            object bid_price
            object ask_price
            list markets_data = []
            list markets_columns = ["Exchange", "Market", "Best Bid Price", "Best Ask Price", "Mid Price"]
        try:
            for market_trading_pair_tuple in market_trading_pair_tuples:
                market, trading_pair, base_asset, quote_asset = market_trading_pair_tuple
                bid_price = market.get_price(trading_pair, False)
                ask_price = market.get_price(trading_pair, True)
                mid_price = (bid_price + ask_price)/2
                markets_data.append([
                    market.display_name,
                    trading_pair,
                    float(bid_price),
                    float(ask_price),
                    float(mid_price)
                ])
            return pd.DataFrame(data=markets_data, columns=markets_columns)

        except Exception:
            self.logger().error("Error formatting market stats.", exc_info=True)

    def wallet_balance_data_frame(self, market_trading_pair_tuples: List[MarketTradingPairTuple]) -> pd.DataFrame:
        cdef:
            ConnectorBase market
            str base_asset
            str quote_asset
            double base_balance
            double quote_balance
            double base_asset_conversion_rate
            double quote_asset_conversion_rate
            list assets_data = []
            list assets_columns = ["Exchange", "Asset", "Total Balance", "Available Balance"]
        try:
            for market_trading_pair_tuple in market_trading_pair_tuples:
                market, trading_pair, base_asset, quote_asset = market_trading_pair_tuple
                base_balance = float(market.get_balance(base_asset))
                quote_balance = float(market.get_balance(quote_asset))
                available_base_balance = float(market.get_available_balance(base_asset))
                available_quote_balance = float(market.get_available_balance(quote_asset))
                assets_data.extend([
                    [market.display_name, base_asset, base_balance, available_base_balance],
                    [market.display_name, quote_asset, quote_balance, available_quote_balance]
                ])

            return pd.DataFrame(data=assets_data, columns=assets_columns)

        except Exception:
            self.logger().error("Error formatting wallet balance stats.", exc_info=True)

    def balance_warning(self, market_trading_pair_tuples: List[MarketTradingPairTuple]) -> List[str]:
        cdef:
            double base_balance
            double quote_balance
            list warning_lines = []
        # Add warning lines on null balances.
        # TO-DO: $Use min order size logic to replace the hard-coded 0.0001 value for each asset.
        for market_trading_pair_tuple in market_trading_pair_tuples:
            base_balance = market_trading_pair_tuple.market.get_balance(market_trading_pair_tuple.base_asset)
            quote_balance = market_trading_pair_tuple.market.get_balance(market_trading_pair_tuple.quote_asset)
            if base_balance <= Decimal("0.0001"):
                warning_lines.append(f"  {market_trading_pair_tuple.market.name} market "
                                     f"{market_trading_pair_tuple.base_asset} balance is too low. Cannot place order.")
            if quote_balance <= Decimal("0.0001"):
                warning_lines.append(f"  {market_trading_pair_tuple.market.name} market "
                                     f"{market_trading_pair_tuple.quote_asset} balance is too low. Cannot place order.")
        return warning_lines

    def network_warning(self, market_trading_pair_tuples: List[MarketTradingPairTuple]) -> List[str]:
        cdef:
            list warning_lines = []
            str trading_pairs
        if not all([market_trading_pair_tuple.market.network_status is NetworkStatus.CONNECTED for
                    market_trading_pair_tuple in market_trading_pair_tuples]):
            trading_pairs = " // ".join([market_trading_pair_tuple.trading_pair for market_trading_pair_tuple in market_trading_pair_tuples])
            warning_lines.extend([
                f"  Markets are offline for the {trading_pairs} pair. Continued trading "
                f"with these markets may be dangerous.",
                ""
            ])
        return warning_lines

    cdef c_start(self, Clock clock, double timestamp):
        TimeIterator.c_start(self, clock, timestamp)
        self._sb_order_tracker.c_start(clock, timestamp)

    cdef c_tick(self, double timestamp):
        TimeIterator.c_tick(self, timestamp)
        self._sb_order_tracker.c_tick(timestamp)

    cdef c_stop(self, Clock clock):
        TimeIterator.c_stop(self, clock)
        self._sb_order_tracker.c_stop(clock)
        self.c_remove_markets(list(self._sb_markets))

    cdef c_add_markets(self, list markets):
        cdef:
            ConnectorBase typed_market

        for market in markets:
            typed_market = market
            typed_market.c_add_listener(self.BUY_ORDER_CREATED_EVENT_TAG, self._sb_create_buy_order_listener)
            typed_market.c_add_listener(self.SELL_ORDER_CREATED_EVENT_TAG, self._sb_create_sell_order_listener)
            typed_market.c_add_listener(self.ORDER_FILLED_EVENT_TAG, self._sb_fill_order_listener)
            typed_market.c_add_listener(self.ORDER_FAILURE_EVENT_TAG, self._sb_fail_order_listener)
            typed_market.c_add_listener(self.ORDER_CANCELLED_EVENT_TAG, self._sb_cancel_order_listener)
            typed_market.c_add_listener(self.ORDER_EXPIRED_EVENT_TAG, self._sb_expire_order_listener)
            typed_market.c_add_listener(self.BUY_ORDER_COMPLETED_EVENT_TAG, self._sb_complete_buy_order_listener)
            typed_market.c_add_listener(self.SELL_ORDER_COMPLETED_EVENT_TAG, self._sb_complete_sell_order_listener)
            self._sb_markets.add(typed_market)

    cdef c_remove_markets(self, list markets):
        cdef:
            ConnectorBase typed_market

        for market in markets:
            typed_market = market
            if typed_market not in self._sb_markets:
                continue
            typed_market.c_remove_listener(self.BUY_ORDER_CREATED_EVENT_TAG, self._sb_create_buy_order_listener)
            typed_market.c_remove_listener(self.SELL_ORDER_CREATED_EVENT_TAG, self._sb_create_sell_order_listener)
            typed_market.c_remove_listener(self.ORDER_FILLED_EVENT_TAG, self._sb_fill_order_listener)
            typed_market.c_remove_listener(self.ORDER_FAILURE_EVENT_TAG, self._sb_fail_order_listener)
            typed_market.c_remove_listener(self.ORDER_CANCELLED_EVENT_TAG, self._sb_cancel_order_listener)
            typed_market.c_remove_listener(self.ORDER_EXPIRED_EVENT_TAG, self._sb_expire_order_listener)
            typed_market.c_remove_listener(self.BUY_ORDER_COMPLETED_EVENT_TAG, self._sb_complete_buy_order_listener)
            typed_market.c_remove_listener(self.SELL_ORDER_COMPLETED_EVENT_TAG, self._sb_complete_sell_order_listener)
            self._sb_markets.remove(typed_market)

    cdef object c_sum_flat_fees(self, str quote_asset, list flat_fees):

        """
        Converts flat fees to quote token and sums up all flat fees
        """
        cdef:
            object total_flat_fees = s_decimal_0

        for flat_fee_currency, flat_fee_amount in flat_fees:
            if flat_fee_currency == quote_asset:
                total_flat_fees += flat_fee_amount
            else:
                # if the flat fee currency asset does not match quote asset, raise exception for now
                # as we don't support different token conversion atm.
                raise Exception("Flat fee in other token than quote asset is not supported.")
        return total_flat_fees

    # <editor-fold desc="+ Market event interfaces">
    # ----------------------------------------------------------------------------------------------------------
    cdef c_did_create_buy_order(self, object order_created_event):
        pass

    cdef c_did_create_sell_order(self, object order_created_event):
        pass

    cdef c_did_fill_order(self, object order_filled_event):
        pass

    cdef c_did_fail_order(self, object order_failed_event):
        pass

    cdef c_did_cancel_order(self, object cancelled_event):
        pass

    cdef c_did_expire_order(self, object expired_event):
        pass

    cdef c_did_complete_buy_order(self, object order_completed_event):
        pass

    cdef c_did_complete_sell_order(self, object order_completed_event):
        pass
    # ----------------------------------------------------------------------------------------------------------
    # </editor-fold>

    # <editor-fold desc="+ Order tracking event handlers">
    # ----------------------------------------------------------------------------------------------------------
    cdef c_did_fail_order_tracker(self, object order_failed_event):
        cdef:
            str order_id = order_failed_event.order_id
            object order_type = order_failed_event.order_type
            object market_pair = self._sb_order_tracker.c_get_market_pair_from_order_id(order_id)

        if order_type.is_limit_type():
            self.c_stop_tracking_limit_order(market_pair, order_id)
        elif order_type == OrderType.MARKET:
            self.c_stop_tracking_market_order(market_pair, order_id)

    cdef c_did_cancel_order_tracker(self, object order_cancelled_event):
        cdef:
            str order_id = order_cancelled_event.order_id
            object market_pair = self._sb_order_tracker.c_get_market_pair_from_order_id(order_id)

        self.c_stop_tracking_limit_order(market_pair, order_id)

    cdef c_did_expire_order_tracker(self, object order_expired_event):
        self.c_did_cancel_order_tracker(order_expired_event)

    cdef c_did_complete_buy_order_tracker(self, object order_completed_event):
        cdef:
            str order_id = order_completed_event.order_id
            object market_pair = self._sb_order_tracker.c_get_market_pair_from_order_id(order_id)
            object order_type = order_completed_event.order_type

        if market_pair is not None:
            if order_type.is_limit_type():
                self.c_stop_tracking_limit_order(market_pair, order_id)
            elif order_type == OrderType.MARKET:
                self.c_stop_tracking_market_order(market_pair, order_id)

    cdef c_did_complete_sell_order_tracker(self, object order_completed_event):
        self.c_did_complete_buy_order_tracker(order_completed_event)

    # ----------------------------------------------------------------------------------------------------------
    # </editor-fold>

    # <editor-fold desc="+ Creating and cancelling orders">
    # ----------------------------------------------------------------------------------------------------------

    def buy_with_specific_market(self, market_trading_pair_tuple, amount,
                                 order_type=OrderType.MARKET,
                                 price=s_decimal_nan,
                                 expiration_seconds=NaN,
                                 position_action=PositionAction.OPEN):
        return self.c_buy_with_specific_market(market_trading_pair_tuple, amount,
                                               order_type,
                                               price,
                                               expiration_seconds,
                                               position_action)

    cdef str c_buy_with_specific_market(self, object market_trading_pair_tuple, object amount,
                                        object order_type=OrderType.MARKET,
                                        object price=s_decimal_nan,
                                        double expiration_seconds=NaN,
                                        position_action=PositionAction.OPEN):
        if self._sb_delegate_lock:
            raise RuntimeError("Delegates are not allowed to execute orders directly.")

        if not (isinstance(amount, Decimal) and isinstance(price, Decimal)):
            raise TypeError("price and amount must be Decimal objects.")

        cdef:
            kwargs = {"expiration_ts": self._current_timestamp + expiration_seconds,
                      "position_action": position_action}
            ConnectorBase market = market_trading_pair_tuple.market

        if market not in self._sb_markets:
            raise ValueError(f"Market object for buy order is not in the whitelisted markets set.")

        cdef:
            str order_id = market.c_buy(market_trading_pair_tuple.trading_pair,
                                        amount=amount,
                                        order_type=order_type,
                                        price=price,
                                        kwargs=kwargs)

        # Start order tracking
        if order_type.is_limit_type():
            self.c_start_tracking_limit_order(market_trading_pair_tuple, order_id, True, price, amount)
        elif order_type == OrderType.MARKET:
            self.c_start_tracking_market_order(market_trading_pair_tuple, order_id, True, amount)

        return order_id

    def sell_with_specific_market(self, market_trading_pair_tuple, amount,
                                  order_type=OrderType.MARKET,
                                  price=s_decimal_nan,
                                  expiration_seconds=NaN,
                                  position_action=PositionAction.OPEN):
        return self.c_sell_with_specific_market(market_trading_pair_tuple, amount,
                                                order_type,
                                                price,
                                                expiration_seconds,
                                                position_action)

    cdef str c_sell_with_specific_market(self, object market_trading_pair_tuple, object amount,
                                         object order_type=OrderType.MARKET,
                                         object price=s_decimal_nan,
                                         double expiration_seconds=NaN,
                                         position_action=PositionAction.OPEN):
        if self._sb_delegate_lock:
            raise RuntimeError("Delegates are not allowed to execute orders directly.")

        if not (isinstance(amount, Decimal) and isinstance(price, Decimal)):
            raise TypeError("price and amount must be Decimal objects.")

        cdef:
            kwargs = {"expiration_ts": self._current_timestamp + expiration_seconds,
                      "position_action": position_action}
            ConnectorBase market = market_trading_pair_tuple.market

        if market not in self._sb_markets:
            raise ValueError(f"Market object for sell order is not in the whitelisted markets set.")

        cdef:
            str order_id = market.c_sell(market_trading_pair_tuple.trading_pair, amount,
                                         order_type=order_type, price=price, kwargs=kwargs)

        # Start order tracking
        if order_type.is_limit_type():
            self.c_start_tracking_limit_order(market_trading_pair_tuple, order_id, False, price, amount)
        elif order_type == OrderType.MARKET:
            self.c_start_tracking_market_order(market_trading_pair_tuple, order_id, False, amount)

        return order_id

    cdef c_cancel_order(self, object market_trading_pair_tuple, str order_id):
        cdef:
            ConnectorBase market = market_trading_pair_tuple.market

        if self._sb_order_tracker.c_check_and_track_cancel(order_id):
            self.log_with_clock(
                logging.INFO,
                f"({market_trading_pair_tuple.trading_pair}) Cancelling the limit order {order_id}."
            )
            market.c_cancel(market_trading_pair_tuple.trading_pair, order_id)
    # ----------------------------------------------------------------------------------------------------------
    # </editor-fold>

    # <editor-fold desc="+ Order tracking entry points">
    # The following exposed tracking functions are meant to allow extending order tracking behavior in strategy
    # classes.
    # ----------------------------------------------------------------------------------------------------------
    cdef c_start_tracking_limit_order(self, object market_pair, str order_id, bint is_buy, object price,
                                      object quantity):
        self._sb_order_tracker.c_start_tracking_limit_order(market_pair, order_id, is_buy, price, quantity)

    cdef c_stop_tracking_limit_order(self, object market_pair, str order_id):
        self._sb_order_tracker.c_stop_tracking_limit_order(market_pair, order_id)

    cdef c_start_tracking_market_order(self, object market_pair, str order_id, bint is_buy, object quantity):
        self._sb_order_tracker.c_start_tracking_market_order(market_pair, order_id, is_buy, quantity)

    cdef c_stop_tracking_market_order(self, object market_pair, str order_id):
        self._sb_order_tracker.c_stop_tracking_market_order(market_pair, order_id)

    cdef c_track_restored_orders(self, object market_pair):
        cdef:
            list limit_orders = market_pair.market.limit_orders
            list restored_order_ids = []

        for order in limit_orders:
            restored_order_ids.append(order.client_order_id)
            self.c_start_tracking_limit_order(market_pair,
                                              order.client_order_id,
                                              order.is_buy,
                                              order.price,
                                              order.quantity)
        return restored_order_ids

    # ----------------------------------------------------------------------------------------------------------
    # </editor-fold>
