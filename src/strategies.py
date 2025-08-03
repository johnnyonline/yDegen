from ape import Contract
from ape.contracts.base import ContractInstance

# BTC_STRATEGIES = [
#     # "0xabc123...btc1",
#     # "0xabc123...btc2",
# ]

ETH_STRATEGIES = [
    "0x6fdF47fb4198677D5B0843e52Cf12B5464cE723E",  # crvUSD WETH LB
]

# ALL_STRATEGY_ADDRESSES = BTC_STRATEGIES + ETH_STRATEGIES
ALL_STRATEGY_ADDRESSES = ETH_STRATEGIES


def all_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in ALL_STRATEGY_ADDRESSES]
