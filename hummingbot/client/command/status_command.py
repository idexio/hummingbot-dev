import pandas as pd
import time
from collections import (
    deque,
    OrderedDict
)
import inspect
from typing import List, Dict
from hummingbot import check_dev_mode
from hummingbot.logger.application_warning import ApplicationWarning
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.core.utils.ethereum import check_web3
from hummingbot.client.config.config_helpers import (
    missing_required_configs,
    get_strategy_config_map
)
from hummingbot.client.config.security import Security
from hummingbot.user.user_balances import UserBalances
from hummingbot.client.settings import required_exchanges, ethereum_wallet_required, ethereum_gas_station_required
from hummingbot.core.utils.async_utils import safe_ensure_future

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from hummingbot.client.hummingbot_application import HummingbotApplication


class StatusCommand:
    def _expire_old_application_warnings(self,  # type: HummingbotApplication
                                         ):
        now: float = time.time()
        expiry_threshold: float = now - self.APP_WARNING_EXPIRY_DURATION
        while len(self._app_warnings) > 0 and self._app_warnings[0].timestamp < expiry_threshold:
            self._app_warnings.popleft()

    def _format_application_warnings(self,  # type: HummingbotApplication
                                     ) -> str:
        lines: List[str] = []
        if len(self._app_warnings) < 1:
            return ""

        lines.append("\n  Warnings:")

        if len(self._app_warnings) < self.APP_WARNING_STATUS_LIMIT:
            for app_warning in reversed(self._app_warnings):
                lines.append(f"    * {pd.Timestamp(app_warning.timestamp, unit='s')} - "
                             f"({app_warning.logger_name}) - {app_warning.warning_msg}")
        else:
            module_based_warnings: OrderedDict = OrderedDict()
            for app_warning in reversed(self._app_warnings):
                logger_name: str = app_warning.logger_name
                if logger_name not in module_based_warnings:
                    module_based_warnings[logger_name] = deque([app_warning])
                else:
                    module_based_warnings[logger_name].append(app_warning)

            warning_lines: List[str] = []
            while len(warning_lines) < self.APP_WARNING_STATUS_LIMIT:
                logger_keys: List[str] = list(module_based_warnings.keys())
                for key in logger_keys:
                    warning_item: ApplicationWarning = module_based_warnings[key].popleft()
                    if len(module_based_warnings[key]) < 1:
                        del module_based_warnings[key]
                    warning_lines.append(f"    * {pd.Timestamp(warning_item.timestamp, unit='s')} - "
                                         f"({key}) - {warning_item.warning_msg}")
            lines.extend(warning_lines[:self.APP_WARNING_STATUS_LIMIT])

        return "\n".join(lines)

    async def strategy_status(self):
        paper_trade = "\n  Paper Trading ON: All orders are simulated, and no real orders are placed." if global_config_map.get("paper_trade_enabled").value \
            else ""
        app_warning = self.application_warning()
        app_warning = "" if app_warning is None else app_warning
        if inspect.iscoroutinefunction(self.strategy.format_status):
            st_status = await self.strategy.format_status()
        else:
            st_status = self.strategy.format_status()
        status = paper_trade + "\n" + st_status + "\n" + app_warning
        if self._script_iterator is not None:
            self._script_iterator.request_status()
        return status

    def application_warning(self):
        # Application warnings.
        self._expire_old_application_warnings()
        if check_dev_mode() and len(self._app_warnings) > 0:
            app_warning = self._format_application_warnings()
            self._notify(app_warning)
            return app_warning

    async def validate_required_connections(self) -> Dict[str, str]:
        invalid_conns = {}
        if self.strategy_name == "celo_arb":
            err_msg = await self.validate_n_connect_celo(True)
            if err_msg is not None:
                invalid_conns["celo"] = err_msg
        if not global_config_map.get("paper_trade_enabled").value:
            await self.update_all_secure_configs()
            connections = await UserBalances.instance().update_exchanges(exchanges=required_exchanges)
            invalid_conns.update({ex: err_msg for ex, err_msg in connections.items()
                                  if ex in required_exchanges and err_msg is not None})
            if ethereum_wallet_required():
                err_msg = UserBalances.validate_ethereum_wallet()
                if err_msg is not None:
                    invalid_conns["ethereum"] = err_msg
        return invalid_conns

    def missing_configurations(self) -> List[str]:
        missing_globals = missing_required_configs(global_config_map)
        missing_configs = missing_required_configs(get_strategy_config_map(self.strategy_name))
        return missing_globals + missing_configs

    def status(self,  # type: HummingbotApplication
               live: bool = False):
        safe_ensure_future(self.status_check_all(live=live), loop=self.ev_loop)

    async def status_check_all(self,  # type: HummingbotApplication
                               notify_success=True,
                               live=False) -> bool:

        if self.strategy is not None:
            if live:
                await self.stop_live_update()
                self.app.live_updates = True
                while self.app.live_updates:
                    script_status = '\n Status from script would not appear here. ' \
                                    'Simply run the status command without "--live" to see script status.'
                    await self.cls_display_delay(
                        await self.strategy_status() + script_status + "\n\n Press escape key to stop update.", 1
                    )
                self._notify("Stopped live status display update.")
            else:
                self._notify(await self.strategy_status())
            return True

        # Preliminary checks.
        self._notify("\nPreliminary checks:")
        if self.strategy_name is None or self.strategy_file_name is None:
            self._notify('  - Strategy check: Please import or create a strategy.')
            return False

        if not Security.is_decryption_done():
            self._notify('  - Security check: Encrypted files are being processed. Please wait and try again later.')
            return False

        invalid_conns = await self.validate_required_connections()
        if invalid_conns:
            self._notify('  - Exchange check: Invalid connections:')
            for ex, err_msg in invalid_conns.items():
                self._notify(f"    {ex}: {err_msg}")
        elif notify_success:
            self._notify('  - Exchange check: All connections confirmed.')

        missing_configs = self.missing_configurations()
        if missing_configs:
            self._notify("  - Strategy check: Incomplete strategy configuration. The following values are missing.")
            for config in missing_configs:
                self._notify(f"    {config.key}")
        elif notify_success:
            self._notify('  - Strategy check: All required parameters confirmed.')
        if invalid_conns or missing_configs:
            return False

        if self.wallet is not None:
            # Only check node url when a wallet has been initialized
            eth_node_valid = check_web3(global_config_map.get("ethereum_rpc_url").value)
            if not eth_node_valid:
                self._notify('  - Node check: Bad ethereum rpc url. '
                             'Please re-configure by entering "config ethereum_rpc_url"')
                return False
            elif notify_success:
                self._notify("  - Node check: Ethereum node running and current.")

            if self.wallet.network_status is NetworkStatus.CONNECTED:
                if self._trading_required:
                    has_minimum_eth = self.wallet.get_balance("ETH") > 0.01
                    if not has_minimum_eth:
                        self._notify("  - ETH wallet check: Not enough ETH in wallet. "
                                     "A small amount of Ether is required for sending transactions on "
                                     "Decentralized Exchanges")
                        return False
                    elif notify_success:
                        self._notify("  - ETH wallet check: Minimum ETH requirement satisfied")
            else:
                self._notify("  - ETH wallet check: ETH wallet is not connected.")

        if ethereum_gas_station_required() and not global_config_map["ethgasstation_gas_enabled"].value:
            self._notify(f'  - ETH gas station check: Manual gas price is fixed at '
                         f'{global_config_map["manual_gas_price"].value}.')

        loading_markets: List[ConnectorBase] = []
        for market in self.markets.values():
            if not market.ready:
                loading_markets.append(market)

        if len(loading_markets) > 0:
            self._notify("  - Connectors check:  Waiting for connectors " +
                         ",".join([m.name.capitalize() for m in loading_markets]) + " to get ready for trading. \n"
                         "                    Please keep the bot running and try to start again in a few minutes. \n")

            for market in loading_markets:
                market_status_df = pd.DataFrame(data=market.status_dict.items(), columns=["description", "status"])
                self._notify(
                    f"  - {market.display_name.capitalize()} connector status:\n" +
                    "\n".join(["     " + line for line in market_status_df.to_string(index=False,).split("\n")]) +
                    "\n"
                )
            return False

        elif not all([market.network_status is NetworkStatus.CONNECTED for market in self.markets.values()]):
            offline_markets: List[str] = [
                market_name
                for market_name, market
                in self.markets.items()
                if market.network_status is not NetworkStatus.CONNECTED
            ]
            for offline_market in offline_markets:
                self._notify(f"  - Connector check: {offline_market} is currently offline.")
            return False

        # Paper trade mode is currently not available for connectors other than exchanges.
        # Todo: This check is hard coded at the moment, when we get a clearer direction on how we should handle this,
        # this section will need updating.
        if global_config_map.get("paper_trade_enabled").value:
            if "balancer" in required_exchanges and \
                    str(global_config_map.get("ethereum_chain_name").value).lower() != "kovan":
                self._notify("Error: Paper trade mode is not available on balancer at the moment.")
                return False
            if "binance_perpetual" in required_exchanges:
                self._notify("Error: Paper trade mode is not available on binance_perpetual at the moment.")
                return False

        self.application_warning()
        self._notify("  - All checks: Confirmed.")
        return True
