from collections.abc import Mapping
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
    strategies: Mapping[str, str | None]  # strategy address → APR oracle (None if not used)
    explorer: str


NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        # Chainlink ETH/USD. New answer is written when the price moves more than 0.5% or every 1 hour
        "oracle": "0x7d4E742018fb52E48b08BE73d041C18B21de6Fb5",
        "strategies": {
            "0x629656a04183aFFdE9449158757D36A8a13cd168": "0x0E40eb56626cFD0f41CA7A72618209D958561e65",  # Curve WETH Lender crvUSD Borrower
        },
        "explorer": "https://etherscan.io/address/",
    },
    "base": {
        # Chainlink ETH/USD. New answer is written when the price moves more than 0.15% or every 20 minutes
        "oracle": "0x57d2d46Fc7ff2A7142d479F2f59e1E3F95447077",
        "strategies": {
            "0xfdB431E661372fA1146efB70bf120ECDed944a78": None,  # Moonwell USDC Lender WETH Borrower
            "0x945Df73d55557Ea23c0c35CD350d8DE3b745287E": None,  # Moonwell USDC Lender cbBTC Borrower
            "0x03c5AfF0cd5e40889d689fD9D9Caff286b1BD7Fb": None,  # Moonwell cbBTC Lender WETH Borrower
            "0xd89A4f020C8d256a2A4B0dC40B36Ee0b27680776": None,  # Moonwell cbETH Lender WETH Borrower
        },
        "explorer": "https://basescan.org/address/",
    },
}


def chain_key() -> str:
    return cast(str, chain.provider.network.ecosystem.name.lower())


def cfg() -> NetworkCfg:
    return NETWORKS.get(chain_key(), NETWORKS["ethereum"])


def strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["strategies"].keys()]


def apr_oracle_for(strategy: str) -> ContractInstance | None:
    addr = cfg()["strategies"].get(strategy)
    if addr:
        return cast(ContractInstance, Contract(addr))
    return None


def oracle() -> ContractInstance:
    return cast(ContractInstance, Contract(cfg()["oracle"]))


def explorer_base_url() -> str:
    return cfg()["explorer"]
