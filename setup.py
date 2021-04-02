#!/usr/bin/env python

from setuptools import setup
from setuptools.command.build_ext import build_ext
from Cython.Build import cythonize
import numpy as np
import os
import subprocess
import sys

is_posix = (os.name == "posix")

if is_posix:
    os_name = subprocess.check_output("uname").decode("utf8")
    if "Darwin" in os_name:
        os.environ["CFLAGS"] = "-stdlib=libc++ -std=c++11"
    else:
        os.environ["CFLAGS"] = "-std=c++11"


# Avoid a gcc warning below:
# cc1plus: warning: command line option ‘-Wstrict-prototypes’ is valid
# for C/ObjC but not for C++
class BuildExt(build_ext):
    def build_extensions(self):
        if os.name != "nt" and '-Wstrict-prototypes' in self.compiler.compiler_so:
            self.compiler.compiler_so.remove('-Wstrict-prototypes')
        super().build_extensions()


def main():
    cpu_count = os.cpu_count() or 8
    version = "20210309"
    packages = [
        "hummingbot",
        "hummingbot.client",
        "hummingbot.client.command",
        "hummingbot.client.config",
        "hummingbot.client.ui",
        "hummingbot.core",
        "hummingbot.core.data_type",
        "hummingbot.core.event",
        "hummingbot.core.management",
        "hummingbot.core.utils",
        "hummingbot.data_feed",
        "hummingbot.logger",
        "hummingbot.market",
        "hummingbot.connector",
        "hummingbot.connector.connector",
        "hummingbot.connector.connector.balancer",
        "hummingbot.connector.connector.terra",
        "hummingbot.connector.exchange",
        "hummingbot.connector.exchange.ascend_ex",
        "hummingbot.connector.exchange.binance",
        "hummingbot.connector.exchange.bitfinex",
        "hummingbot.connector.exchange.bittrex",
        "hummingbot.connector.exchange.bamboo_relay",
        "hummingbot.connector.exchange.coinbase_pro",
        "hummingbot.connector.exchange.idex",
        "hummingbot.connector.exchange.dydx",
        "hummingbot.connector.exchange.huobi",
        "hummingbot.connector.exchange.radar_relay",
        "hummingbot.connector.exchange.kraken",
        "hummingbot.connector.exchange.crypto_com",
        "hummingbot.connector.exchange.kucoin",
        "hummingbot.connector.exchange.loopring",
        "hummingbot.connector.exchange.okex",
        "hummingbot.connector.exchange.liquid",
        "hummingbot.connector.exchange.dolomite",
        "hummingbot.connector.exchange.eterbase",
        "hummingbot.connector.exchange.beaxy",
        "hummingbot.connector.exchange.hitbtc",
        "hummingbot.connector.derivative",
        "hummingbot.connector.derivative.binance_perpetual",
        "hummingbot.script",
        "hummingbot.strategy",
        "hummingbot.strategy.amm_arb",
        "hummingbot.strategy.arbitrage",
        "hummingbot.strategy.cross_exchange_market_making",
        "hummingbot.strategy.pure_market_making",
        "hummingbot.strategy.perpetual_market_making",
        "hummingbot.templates",
        "hummingbot.wallet",
        "hummingbot.wallet.ethereum",
        "hummingbot.wallet.ethereum.uniswap",
        "hummingbot.wallet.ethereum.watcher",
        "hummingbot.wallet.ethereum.zero_ex",
    ]
    package_data = {
        "hummingbot": [
            "core/cpp/*",
            "wallet/ethereum/zero_ex/*.json",
            "wallet/ethereum/token_abi/*.json",
            "wallet/ethereum/erc20_tokens.json",
            "wallet/ethereum/erc20_tokens_kovan.json",
            "VERSION",
            "templates/*TEMPLATE.yml"
        ],
    }
    install_requires = [
        "aioconsole",
        "aiokafka",
        "attrdict",
        "cytoolz",
        "eth-abi",
        "eth-account",
        "eth-bloom",
        "eth-hash",
        "eth-keyfile",
        "eth-keys",
        "eth-rlp",
        "eth-utils",
        "hexbytes",
        "kafka-python",
        "lru-dict",
        "parsimonious",
        "pycryptodome",
        "requests",
        "rlp",
        "toolz",
        "tzlocal",
        "urllib3",
        "web3",
        "websockets",
        "aiohttp",
        "async-timeout",
        "attrs",
        "certifi",
        "chardet",
        "cython==0.29.15",
        "idna",
        "idna_ssl",
        "multidict",
        "numpy",
        "pandas",
        "pytz",
        "pyyaml",
        "python-binance==0.7.5",
        "sqlalchemy",
        "ujson",
        "yarl",
    ]

    cython_kwargs = {
        "language": "c++",
        "language_level": 3,
    }

    if is_posix:
        cython_kwargs["nthreads"] = cpu_count

    if "DEV_MODE" in os.environ:
        version += ".dev1"
        package_data[""] = [
            "*.pxd", "*.pyx", "*.h"
        ]
        package_data["hummingbot"].append("core/cpp/*.cpp")

    if len(sys.argv) > 1 and sys.argv[1] == "build_ext" and is_posix:
        sys.argv.append(f"--parallel={cpu_count}")

    setup(name="hummingbot",
          version=version,
          description="Hummingbot",
          url="https://github.com/CoinAlpha/hummingbot",
          author="CoinAlpha, Inc.",
          author_email="dev@hummingbot.io",
          license="Apache 2.0",
          packages=packages,
          package_data=package_data,
          install_requires=install_requires,
          ext_modules=cythonize(["hummingbot/**/*.pyx"], **cython_kwargs),
          include_dirs=[
              np.get_include()
          ],
          scripts=[
              "bin/hummingbot.py",
              "bin/hummingbot_quickstart.py"
          ],
          cmdclass={'build_ext': BuildExt},
          )


if __name__ == "__main__":
    main()
