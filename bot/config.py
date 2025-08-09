from collections.abc import Mapping, Sequence
from typing import TypedDict, cast

from ape import Contract, chain
from ape.contracts.base import ContractInstance

# fmt: off
EMOJIS = [
    "🦍", "🐒", "🦧", "🐶", "🐱", "🦁", "🐴", "🦄", "🐮",
    "🐖", "🐑", "🐫", "🦒", "🐇", "🦔", "🐨", "🦦", "🦩", "🦭", "🐢", "🐳", "🐡",
]
# fmt: on


class NetworkCfg(TypedDict):
    oracle: str
    strategies: Sequence[str]
    explorer: str


NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        # Chainlink ETH/USD. New answer is written when the price moves more than 0.5% or every 1 hour
        "oracle": "0x7d4E742018fb52E48b08BE73d041C18B21de6Fb5",
        "strategies": [
            "0x629656a04183aFFdE9449158757D36A8a13cd168",  # Curve WETH Lender crvUSD Borrower
        ],
        "explorer": "https://etherscan.io/address/",
    },
    "base": {
        # Chainlink ETH/USD. New answer is written when the price moves more than 0.15% or every 20 minutes
        "oracle": "0x57d2d46Fc7ff2A7142d479F2f59e1E3F95447077",
        "strategies": [
            "0xfdB431E661372fA1146efB70bf120ECDed944a78",  # Moonwell USDC Lender WETH Borrower
            "0x945Df73d55557Ea23c0c35CD350d8DE3b745287E",  # Moonwell USDC Lender cbBTC Borrower
            "0x03c5AfF0cd5e40889d689fD9D9Caff286b1BD7Fb",  # Moonwell cbBTC Lender WETH Borrower
            "0xd89A4f020C8d256a2A4B0dC40B36Ee0b27680776",  # Moonwell cbETH Lender WETH Borrower
        ],
        "explorer": "https://basescan.org/address/",
    },
}


def chain_key() -> str:
    return cast(str, chain.provider.network.ecosystem.name.lower())


def cfg() -> NetworkCfg:
    return NETWORKS.get(chain_key(), NETWORKS["ethereum"])


def strategies() -> list[ContractInstance]:
    addrs: Sequence[str] = cfg()["strategies"]
    return [Contract(addr) for addr in addrs]


def oracle() -> ContractInstance:
    return cast(ContractInstance, Contract(cfg()["oracle"]))


def explorer_base_url() -> str:
    return cfg()["explorer"]
