#!/usr/bin/env python

connector_status = {
    'balancer': 'green',
    'beaxy': 'yellow',
    'binance': 'green',
    'binance_perpetual': 'green',
    'binance_perpetual_testnet': 'green',
    'binance_us': 'yellow',
    'bitfinex': 'yellow',
    'ascend_ex': 'green',
    'bittrex': 'yellow',
    'blocktane': 'green',
    'celo': 'green',
    'coinbase_pro': 'green',
    'crypto_com': 'yellow',
    'dydx': 'green',
    'eterbase': 'red',
    'ethereum': 'red',
    'hitbtc': 'yellow',
    'huobi': 'green',
    'idex': 'green',
    'kraken': 'yellow',
    'kucoin': 'green',
    'liquid': 'green',
    'loopring': 'yellow',
    'okex': 'green',
    'perpetual_finance': 'yellow',
    'probit': 'yellow',
    'probit_kr': 'yellow',
    'terra': 'green',
    'uniswap': 'green'
}

warning_messages = {
    'eterbase': 'Hack investigation and security audit is ongoing for Eterbase. Trading is currently disabled.'
}


def get_connector_status(connector_name: str) -> str:
    """
    Indicator whether a connector is working properly or not.
    UNKNOWN means the connector is not in connector_status dict.
    RED means a connector doesn't work.
    YELLOW means the connector is either new or has one or more issues.
    GREEN means a connector is working properly.
    """
    if connector_name not in connector_status.keys():
        status = "UNKNOWN"
    else:
        return connector_status[connector_name].upper()
    return status
