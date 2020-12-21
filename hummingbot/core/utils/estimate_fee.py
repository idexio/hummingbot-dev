from decimal import Decimal
from hummingbot.core.event.events import TradeFee, TradeFeeType
from hummingbot.client.config.fee_overrides_config_map import fee_overrides_config_map
from hummingbot.client.settings import CONNECTOR_SETTINGS
from hummingbot.core.utils.eth_gas_station_lookup import get_gas_price, get_gas_limit


def estimate_fee(exchange: str, is_maker: bool) -> TradeFee:
    if exchange not in CONNECTOR_SETTINGS:
        raise Exception(f"Invalid connector. {exchange} does not exist in CONNECTOR_SETTINGS")
    use_gas = CONNECTOR_SETTINGS[exchange].use_eth_gas_lookup
    if use_gas:
        gas_amount = get_gas_price(in_gwei=False) * get_gas_limit(exchange)
        return TradeFee(percent=0, flat_fees=[("ETH", gas_amount)])
    fee_type = CONNECTOR_SETTINGS[exchange].fee_type
    fee_token = CONNECTOR_SETTINGS[exchange].fee_token
    default_fees = CONNECTOR_SETTINGS[exchange].default_fees
    fee_side = "maker" if is_maker else "taker"
    override_key = f"{exchange}_{fee_side}"
    if fee_type is TradeFeeType.FlatFee:
        override_key += "_fee_amount"
    elif fee_type is TradeFeeType.Percent:
        override_key += "_fee"
    fee = default_fees[0] if is_maker else default_fees[1]
    fee_config = fee_overrides_config_map.get(override_key)
    if fee_config is not None and fee_config.value is not None:
        fee = fee_config.value
    fee = Decimal(str(fee))
    if fee_type is TradeFeeType.Percent:
        return TradeFee(percent=fee / Decimal("100"), flat_fees=[])
    elif fee_type is TradeFeeType.FlatFee:
        return TradeFee(percent=0, flat_fees=[(fee_token, fee)])
