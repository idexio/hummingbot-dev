import argparse
from typing import (
    List,
)
from hummingbot.client.errors import ArgumentParserError
from hummingbot.client.command.connect_command import OPTIONS as CONNECT_OPTIONS


class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)

    def exit(self, status=0, message=None):
        pass

    def print_help(self, file=None):
        pass

    @property
    def subparser_action(self):
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                return action

    @property
    def commands(self) -> List[str]:
        return list(self.subparser_action._name_parser_map.keys())

    def subcommands_from(self, top_level_command: str) -> List[str]:
        parser: argparse.ArgumentParser = self.subparser_action._name_parser_map.get(top_level_command)
        if parser is None:
            return []
        subcommands = parser._optionals._option_string_actions.keys()
        filtered = list(filter(lambda sub: sub.startswith("--") and sub != "--help", subcommands))
        return filtered


def load_parser(hummingbot) -> ThrowingArgumentParser:
    parser = ThrowingArgumentParser(prog="", add_help=False)
    subparsers = parser.add_subparsers()

    connect_parser = subparsers.add_parser("connect", help="List available exchanges and add API keys to them")
    connect_parser.add_argument("option", nargs="?", choices=CONNECT_OPTIONS, help="Name of the exchange that you want to connect")
    connect_parser.set_defaults(func=hummingbot.connect)

    create_parser = subparsers.add_parser("create", help="Create a new bot")
    create_parser.add_argument("file_name", nargs="?", default=None, help="Name of the configuration file")
    create_parser.set_defaults(func=hummingbot.create)

    import_parser = subparsers.add_parser("import", help="Import an existing bot by loading the configuration file")
    import_parser.add_argument("file_name", nargs="?", default=None, help="Name of the configuration file")
    import_parser.set_defaults(func=hummingbot.import_command)

    help_parser = subparsers.add_parser("help", help="List available commands")
    help_parser.add_argument("command", nargs="?", default="all", help="Enter ")
    help_parser.set_defaults(func=hummingbot.help)

    balance_parser = subparsers.add_parser("balance", help="Display your asset balances across all connected exchanges")
    balance_parser.add_argument("option", nargs="?", choices=["limit", "paper"], default=None,
                                help="Option for balance configuration")
    balance_parser.add_argument("args", nargs="*")
    balance_parser.set_defaults(func=hummingbot.balance)

    config_parser = subparsers.add_parser("config", help="Display the current bot's configuration")
    config_parser.add_argument("key", nargs="?", default=None, help="Name of the parameter you want to change")
    config_parser.add_argument("value", nargs="?", default=None, help="New value for the parameter")
    config_parser.set_defaults(func=hummingbot.config)

    start_parser = subparsers.add_parser("start", help="Start the current bot")
    start_parser.add_argument("--restore", default=False, action="store_true", dest="restore", help="Restore and maintain any active orders.")
    # start_parser.add_argument("--log-level", help="Level of logging")
    start_parser.set_defaults(func=hummingbot.start)

    stop_parser = subparsers.add_parser('stop', help="Stop the current bot")
    stop_parser.set_defaults(func=hummingbot.stop)

    open_orders_parser = subparsers.add_parser('open_orders', help="Show all active open orders")
    open_orders_parser.add_argument("-f", "--full_report", default=False, action="store_true",
                                    dest="full_report", help="Show full report with size comparison")
    open_orders_parser.set_defaults(func=hummingbot.open_orders)

    trades_parser = subparsers.add_parser('trades', help="Show trades")
    trades_parser.add_argument("-d", "--days", type=float, default=1., dest="days",
                               help="How many days in the past (can be decimal value)")
    trades_parser.add_argument("-m", "--market", default=None,
                               dest="market", help="The market you want to see trades.")
    trades_parser.add_argument("-o", "--open_order_markets", default=False, action="store_true",
                               dest="open_order_markets", help="See trades from current open order markets.")
    trades_parser.set_defaults(func=hummingbot.trades)

    pnl_parser = subparsers.add_parser('pnl', help="Show profits and losses")
    pnl_parser.add_argument("-d", "--days", type=float, default=1., dest="days",
                            help="How many days in the past (can be decimal value)")
    pnl_parser.add_argument("-m", "--market", default=None,
                            dest="market", help="The market you want to see trades.")
    pnl_parser.add_argument("-o", "--open_order_markets", default=False, action="store_true",
                            dest="open_order_markets", help="See PnL from current open order markets.")
    pnl_parser.set_defaults(func=hummingbot.pnl)

    status_parser = subparsers.add_parser("status", help="Get the market status of the current bot")
    status_parser.add_argument("--live", default=False, action="store_true", dest="live", help="Show status updates")
    status_parser.set_defaults(func=hummingbot.status)

    history_parser = subparsers.add_parser("history", help="See the past performance of the current bot")
    history_parser.add_argument("-d", "--days", type=float, default=0, dest="days",
                                help="How many days in the past (can be decimal value)")
    history_parser.add_argument("-v", "--verbose", action="store_true", default=False,
                                dest="verbose", help="List all trades")
    history_parser.add_argument("-p", "--precision", default=None, type=int,
                                dest="precision", help="Level of precions for values displayed")
    history_parser.set_defaults(func=hummingbot.history)

    generate_certs_parser = subparsers.add_parser("generate_certs", help="Create SSL certifications "
                                                                         "for Gateway communication.")
    generate_certs_parser.set_defaults(func=hummingbot.generate_certs)

    exit_parser = subparsers.add_parser("exit", help="Exit and cancel all outstanding orders")
    exit_parser.add_argument("-f", "--force", "--suspend", action="store_true", help="Force exit without cancelling outstanding orders",
                             default=False)
    exit_parser.set_defaults(func=hummingbot.exit)

    paper_trade_parser = subparsers.add_parser("paper_trade", help="Toggle paper trade mode on and off")
    paper_trade_parser.set_defaults(func=hummingbot.paper_trade)

    export_parser = subparsers.add_parser("export", help="Export secure information")
    export_parser.add_argument("option", nargs="?", choices=("keys", "trades"), help="Export choices")
    export_parser.set_defaults(func=hummingbot.export)

    order_book_parser = subparsers.add_parser("order_book", help="Display current order book")
    order_book_parser.add_argument("--lines", type=int, default=5, dest="lines", help="Number of lines to display")
    order_book_parser.add_argument("--exchange", type=str, dest="exchange", help="The exchange of the market")
    order_book_parser.add_argument("--market", type=str, dest="market", help="The market (trading pair) of the order book")
    order_book_parser.add_argument("--live", default=False, action="store_true", dest="live", help="Show order book updates")
    order_book_parser.set_defaults(func=hummingbot.order_book)

    ticker_parser = subparsers.add_parser("ticker", help="Show market ticker of current order book")
    ticker_parser.add_argument("--live", default=False, action="store_true", dest="live", help="Show ticker updates")
    ticker_parser.add_argument("--exchange", type=str, dest="exchange", help="The exchange of the market")
    ticker_parser.add_argument("--market", type=str, dest="market", help="The market (trading pair) of the order book")
    ticker_parser.set_defaults(func=hummingbot.ticker)

    return parser
