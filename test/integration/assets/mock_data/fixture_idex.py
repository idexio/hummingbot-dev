import json


class FixtureIdex:
    # General Exchange Info
    MARKETS = None

    # General User Info
    BALANCES = [
        {
            "asset": "UNI",
            "quantity": "38192.94678100",
            "availableForTrade": "26710.66678121",
            "locked": "11482.28000000",
            "usdValue": "38188.22"
        },
        {
            "asset": "QNT",
            "quantity": "374.94348200",
            "availableForTrade": "110.86384321",
            "locked": "264.07963879",
            "usdValue": "388.22"
        },
    ]

    # Trade fees found in the exchange api request
    TRADE_FEES = {
        "timeZone": "UTC",
        "serverTime": 1590408000000,
        "ethereumDepositContractAddress": "0x...",
        "ethUsdPrice": "206.46",
        "gasPrice": 7,
        "volume24hUsd": "10416227.98",
        "makerFeeRate": "0.001",
        "takerFeeRate": "0.002",
        "makerTradeMinimum": "0.15000000",
        "takerTradeMinimum": "0.05000000",
        "withdrawalMinimum": "0.04000000"
    }

    ORDERS_STATUS = []

    LISTEN_KEY = None

    # User Trade Info
    # Sample snapshot for trading pair ETH-USDC with sequence = 71228121

    SNAPSHOT_1 = {
        "sequence": 71228121,
        "bids": [
            ["202.00200000", "13.88204000", 2],
            ["202.00100000", "10.00000000", 3],
            ["198.02200000", "9.88204000", 2],
            ["196.10100000", "3.00000000", 9],

        ],
        "asks": [
            ["202.01000000", "4.11400000", 1],
            ["202.01200000", "7.50550000", 3],
            ["204.01000000", "8.11400000", 3],
            ["205.91200000", "12.60550000", 3],
            ["207.31000000", "8.11400000", 2],
            ["210.01200000", "13.50550000", 3],
        ]
    }

    # Sample snapshot for trading pair ETH-USDC with sequence = 71228122
    SNAPSHOT_2 = {
        "sequence": 71228122,
        "bids": [
            ["203.90200000", "9.88204000", 5],
            ["201.30100000", "6.00000000", 1],
            ["199.42200000", "7.88204000", 2],
            ["196.50100000", "2.00000000", 5],

        ],
        "asks": [
            ["204.11000000", "2.11400000", 1],
            ["205.01200000", "3.50550000", 7],
            ["206.01000000", "5.11400000", 5],
            ["208.91200000", "1.60550000", 2],
            ["210.31000000", "2.11400000", 1],
            ["211.01200000", "1.50550000", 3],
        ]
    }

    TRADING_PAIR_TRADES = [
        {
            "fillId": "3e3a7887-2c20-3705-95f4-8a64892612f3",
            "price": "0.00729011",
            "quantity": "200.00000000",
            "quoteQuantity": "1.45802200",
            "time": 1612385689385,
            "makerSide": "buy",
            "sequence": 7
        },
        {
            "fillId": "71ae1754-b92d-336c-9e82-15e1be7f3e01",
            "price": "0.01429000",
            "quantity": "37.21253813",
            "quoteQuantity": "0.53176716",
            "time": 1613839046778,
            "makerSide": "sell",
            "sequence": 8
        },
        {
            "fillId": "4b6a09ec-6fd5-3eb5-ba76-1ce2f1f85c4e",
            "price": "0.01780000",
            "quantity": "115.84889933",
            "quoteQuantity": "2.06211040",
            "time": 1614860652110,
            "makerSide": "sell",
            "sequence": 9
        }
    ]

    TRADING_PAIR_TICKER = {
        "market": "UNI-ETH",
        "time": 1614888274602,
        "open": "0.01780000",
        "high": "0.01780000",
        "low": "0.01780000",
        "close": "0.01780000",
        "closeQuantity": "115.84889933",
        "baseVolume": "115.84889933",
        "quoteVolume": "2.06211040",
        "percentChange": "0.00",
        "numTrades": 1,
        "ask": "0.02480000",
        "bid": "0.00755001",
        "sequence": 9
    }

    ORDER_BOOK_LEVEL2 = {
        "sequence": 39902171,
        "bids": [
            [
                "0.01850226",
                "172.86097063",
                1
            ],
            [
                "0.01850225",
                "540.47480710",
                1
            ]
        ],
        "asks": [
            [
                "0.02091798",
                "112.02217000",
                1
            ],
            [
                "0.02091799",
                "1607.13503722",
                2
            ]
        ]
    }

    WS_PRICE_LEVEL_UPDATE_1 = json.dumps({
        "type": "l2orderbook",
        "data": {
            "m": "ETH-USDC",
            "t": 1590393540000,
            "u": 71228110,
            "b": [["202.00100000", "10.00000000", 1]],
            "a": []
        }
    })

    WS_PRICE_LEVEL_UPDATE_2 = json.dumps({
        "type": "l2orderbook",
        "data": {
            "m": "BAL-ETH",
            "t": 1590383943830,
            "u": 73848374,
            "b": [["198.00100000", "8.00000000", 2]],
            "a": []
        }
    })

    WS_SUBSCRIPTION_SUCCESS = json.dumps({
        "type": "subscriptions",
        "subscriptions": [{"name": "l2orderbook",
                           "markets": ["ETH-USDC"]
                           }]
    })

    WS_TRADE_1 = json.dumps({
        "type": "trades",
        "data": {
            "m": "ETH-USDC",
            "i": "a0b6a470-a6bf-11ea-90a3-8de307b3b6da",
            "p": "202.74900000",
            "q": "10.00000000",
            "Q": "2027.49000000",
            "t": 1590394500000,
            "s": "sell",
            "u": 848778
        }
    })

    WS_TRADE_2 = json.dumps({
        "type": "trades",
        "data": {
            "m": "QNT-ETH",
            "i": "d357a470-a6bf-11ea-90a3-8de3034936da",
            "p": "154.82400000",
            "q": "8.00000000",
            "Q": "1163.53000000",
            "t": 1590387400000,
            "s": "buy",
            "u": 921943
        }
    })