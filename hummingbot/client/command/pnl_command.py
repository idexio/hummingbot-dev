from decimal import Decimal
import pandas as pd
import threading
from typing import (
    TYPE_CHECKING,
    List,
)
from datetime import datetime
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.client.config.security import Security
from hummingbot.user.user_balances import UserBalances
from hummingbot.core.utils.market_price import usd_value
from hummingbot.core.data_type.trade import Trade
from hummingbot.core.data_type.common import OpenOrder
from hummingbot.client.performance import calculate_performance_metrics
from hummingbot.core.utils.market_price import get_last_price
from hummingbot.client.command.history_command import get_timestamp
from hummingbot.client.config.global_config_map import global_config_map

s_float_0 = float(0)
s_decimal_0 = Decimal("0")

if TYPE_CHECKING:
    from hummingbot.client.hummingbot_application import HummingbotApplication


class PnlCommand:
    def pnl(self,  # type: HummingbotApplication
            days: float,
            market: str,
            open_order_markets: bool
            ):
        if threading.current_thread() != threading.main_thread():
            self.ev_loop.call_soon_threadsafe(self.trades)
            return
        safe_ensure_future(self.pnl_report(days, market, open_order_markets))

    async def get_binance_connector(self):
        if self._binance_connector is not None:
            return self._binance_connector
        api_keys = await Security.api_keys("binance")
        if not api_keys:
            return None
        self._binance_connector = UserBalances.connect_market("binance", **api_keys)
        return self._binance_connector

    async def pnl_report(self,  # type: HummingbotApplication
                         days: float,
                         market: str,
                         open_order_markets: bool
                         ):
        exchange = "binance"
        connector = await self.get_binance_connector()
        cur_balances = await self.get_current_balances(exchange)
        if connector is None:
            self._notify("This command supports only binance (for now), please first connect to binance.")
            return
        if market is not None:
            market = market.upper()
            trades: List[Trade] = await connector.get_my_trades(market, days)
            cur_price = await get_last_price(exchange, market)
            perf = calculate_performance_metrics(market, trades, cur_balances, cur_price)
            self.report_performance_by_market(exchange, market, perf, precision=None)
            return
        self._notify(f"Starting: {datetime.fromtimestamp(get_timestamp(days)).strftime('%Y-%m-%d %H:%M:%S')}"
                     f"    Ending: {datetime.fromtimestamp(get_timestamp(0)).strftime('%Y-%m-%d %H:%M:%S')}")
        self._notify("Calculating profit and losses....")
        if open_order_markets:
            orders: List[OpenOrder] = await connector.get_open_orders()
            markets = {o.trading_pair for o in orders}
        else:
            markets = set(global_config_map["binance_markets"].value.split(","))
        markets = sorted(markets)
        data = []
        columns = ["Market", " Traded ($)", " Fee ($)", " PnL ($)", " Return %"]
        for market in markets:
            base, quote = market.split("-")
            trades: List[Trade] = await connector.get_my_trades(market, days)
            if not trades:
                continue
            cur_price = await get_last_price(exchange, market)
            perf = calculate_performance_metrics(market, trades, cur_balances, cur_price)
            volume = await usd_value(quote, abs(perf.b_vol_quote) + abs(perf.s_vol_quote))
            fee = await usd_value(perf.fee_token, perf.fee_paid)
            pnl = await usd_value(quote, perf.total_pnl)
            data.append([market, round(volume, 2), round(fee, 2), round(pnl, 2), f"{perf.return_pct:.2%}"])
        if not data:
            self._notify(f"No trades during the last {days} day(s).")
            return
        lines = []
        df: pd.DataFrame = pd.DataFrame(data=data, columns=columns)
        lines.extend(["    " + line for line in df.to_string(index=False).split("\n")])
        self._notify("\n" + "\n".join(lines))
        self._notify(f"\n  Total PnL: $ {df[' PnL ($)'].sum():.2f}    Total fee: $ {df[' Fee ($)'].sum():.2f}")
