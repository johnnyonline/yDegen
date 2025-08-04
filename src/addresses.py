from typing import cast

from ape import Contract
from ape.contracts.base import ContractInstance

EMOJIS = [
    "🦍",
    "🐒",
    "🦧",
    "🐶",
    "🐱",
    "🦁",
    "🐴",
    "🦄",
    "🐮",
    "🐖",
    "🐑",
    "🐫",
    "🦒",
    "🐇",
    "🦔",
    "🐨",
    "🦦",
    "🦩",
    "🦭",
    "🐢",
    "🐳",
    "🐡",
]

# Chainlink ETH/USD aggregator address. New answer is written when the price moves more than 0.5% or every 1 hour
ETH_ORACLE_ADDRESS = "0x7d4E742018fb52E48b08BE73d041C18B21de6Fb5"

ETH_STRATEGIES = [
    "0x6fdF47fb4198677D5B0843e52Cf12B5464cE723E",  # crvUSD WETH LB
]

ALL_STRATEGY_ADDRESSES = ETH_STRATEGIES


def strategies(asset: str | None = None) -> list[ContractInstance]:
    match asset:
        case "eth":
            return [Contract(addr) for addr in ETH_STRATEGIES]
        case _:
            return [Contract(addr) for addr in ALL_STRATEGY_ADDRESSES]


def eth_oracle() -> ContractInstance:
    return cast(ContractInstance, Contract(ETH_ORACLE_ADDRESS))
