from collections.abc import Mapping, Sequence
from typing import TypedDict, cast

from ape import Contract, chain
from ape.contracts.base import ContractInstance

# fmt: off
EMOJIS = [
    "🦍", "🐒", "🦧", "🐶", "🐱", "🦁", "🐴", "🦄", "🐮",
    "🐑", "🐫", "🦒", "🐇", "🦔", "🐨", "🦦", "🦩", "🦭", "🐢", "🐳", "🐡",
]
# fmt: on


class NetworkCfg(TypedDict):
    lender_borrowers: Sequence[str]
    ybold: Sequence[str]
    explorer: str

NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        "lender_borrowers": [
            "0x6dec370EfA894d48D8C55012B0Cd6f3C1C7C4616",  # Asymmetry tBTC Lender USDaf Borrower
            "0x48E560AfB1482f63e5e8C0eA7fBdd8Fd82054eC3",  # Curve WETH Lender crvUSD Borrower
            "0x4727a60cb92bE2660A1BE082E3E830eaEF97f2d0",  # Curve wstETH Lender crvUSD Borrower
            "0xBc7998142b446beaE87cfd024A94320907eb64b1",  # Curve WBTC Lender crvUSD Borrower
            "0xF556ACeaeaC54b2c3734bb70b8D1Bae0b0580f26",  # Morpho WBTC/yvUSDC-1 Lender Borrower
            "0xD0904a032d0418f32b8Ae6dc984995A0b36d43F9",  # Morpho WBTC/yvUSDT-1 Lender Borrower
            "0x8dd272624392417830CA1a2DcbfDd7d1E14d3887",  # Morpho OETH/yvUSDC-1 Lender Borrower
        ],
        "ybold": [
            "0x2048A730f564246411415f719198d6f7c10A7961",  # yBOLD's WETH Strategy
            "0x46af61661B1e15DA5bFE40756495b7881F426214",  # yBOLD's wstETH Strategy
            "0x2351E217269A4a53a392bffE8195Efa1c502A1D2",  # yBOLD's rETH Strategy
            "0xad7D5D31Ffcb96f6F719Bb78209019d3d09e6baa",  # sUSDaf's ysyBOLD Strategy
            "0xF6516d45A1625a6d9d3479902a5CB4c8B79F1887",  # sUSDaf's sUSDS Strategy
            "0x388095a341Bf5767d3d3B7093cd89A82B816B507",  # sUSDaf's sfrxETH Strategy
            "0xb00a77045574f42b9Aff25dB275af4d5d25146bb",  # sUSDaf's tBTC Strategy
            "0x1d53B127629AF8df7da5488833a50c2F12692F5C",  # sUSDaf's WBTC18 Strategy
        ],
        "explorer": "https://etherscan.io/address/",
    },
    "base": {
        "lender_borrowers": [
            # "0xfdB431E661372fA1146efB70bf120ECDed944a78",  # Moonwell USDC Lender WETH Borrower
            # "0x945Df73d55557Ea23c0c35CD350d8DE3b745287E",  # Moonwell USDC Lender cbBTC Borrower
            # "0x03c5AfF0cd5e40889d689fD9D9Caff286b1BD7Fb",  # Moonwell cbBTC Lender WETH Borrower
            # "0xd89A4f020C8d256a2A4B0dC40B36Ee0b27680776",  # Moonwell cbETH Lender WETH Borrower
        ],
        "ybold": [],
        "explorer": "https://basescan.org/address/",
    },
    "arbitrum": {
        "lender_borrowers": [],
        "ybold": [
            "0xe037A8F2Fa17293d94620c1846F84d047379660a",  # yUSND's WETH Strategy
            "0x533337c57dFA768F4B4827048b320aa78D909D30",  # yUSND's wstETH Strategy
            "0xDAbdD3BD55d55927847510703C0fd7Eb0Af98f52",  # yUSND's rETH Strategy
            "0xAe55FbdC3Cce38464e6A7F23d19A143898451105",  # yUSND's rsETH Strategy
            "0x0d350027AE6fa715f17ea413D053eab94432D730",  # yUSND's weETH Strategy
            "0x013a32B271fA2e51D685CCbEc5493b02162075A2",  # yUSND's ARB Strategy
            "0x38Bcb6856AD0f887Fe05DBE341B8FBd9bBb65cE9",  # yUSND's COMP Strategy
            "0x15B89e3E1C19e76d6bBD39A7b7c1f2f83C9B3Afc",  # yUSND's tBTC Strategy
        ],
        "explorer": "https://arbiscan.io/address/",
    },
}

APR_ORACLE_ADDRESS = "0x1981AD9F44F2EA9aDd2dC4AD7D075c102C70aF92"


def apr_oracle() -> ContractInstance:
    return cast(ContractInstance, Contract(APR_ORACLE_ADDRESS))


def chain_key() -> str:
    return cast(str, chain.provider.network.ecosystem.name.lower())


def cfg() -> NetworkCfg:
    return NETWORKS.get(chain_key(), NETWORKS["ethereum"])


def lender_borrower_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["lender_borrowers"]]


def ybold_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["ybold"]]


def strategies() -> list[ContractInstance]:
    return lender_borrower_strategies() + ybold_strategies()


def explorer_base_url() -> str:
    return cfg()["explorer"]
