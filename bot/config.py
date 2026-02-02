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
    liquity_lender_borrowers: Mapping[str, int]  # address -> collIndex
    ybold: Sequence[str]
    explorer: str
    relayer: str | None


NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        "lender_borrowers": [
            "0x6dec370EfA894d48D8C55012B0Cd6f3C1C7C4616",  # Asymmetry tBTC Lender USDaf Borrower
            "0xf6151034BEc135059E5A6Ccff43317652960ad41",  # Curve WETH/crvUSD Lender Borrower
            "0xB3ef10D305A6CdbC5f19244de528d025F856EF6A",  # Curve wstETH/crvUSD Lender Borrower
            "0x5cee43aa4Beb43E114C50d2127b206a6b95F1151",  # Curve WBTC/crvUSD Lender Borrower
            "0x68D01e2915c39b85EFE691dbb87bF93C6194A4a0",  # Morpho WBTC/yvUSD Lender Borrower
            "0x9da810867E4AA706e02318Bf7869f8530af663ad",  # Morpho WBTC/yvUSDT-1 Lender Borrower
            "0xc5976A234574A7345EfcbB3B0AaF5F435355d2DB",  # Morpho OETH/yvUSDC-1 Lender Borrower
        ],
        "liquity_lender_borrowers": {
            "0x2fFff76ee152164f4dEfc95fB0cf88528251aB9E": 2,  # Liquity rETH/BOLD Lender Borrower (collIndex=2)
        },
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
        "relayer": "0x604e586F17cE106B64185A7a0d2c1Da5bAce711E",
    },
    "base": {
        "lender_borrowers": [
            # "0xfdB431E661372fA1146efB70bf120ECDed944a78",  # Moonwell USDC Lender WETH Borrower
            # "0x945Df73d55557Ea23c0c35CD350d8DE3b745287E",  # Moonwell USDC Lender cbBTC Borrower
            # "0x03c5AfF0cd5e40889d689fD9D9Caff286b1BD7Fb",  # Moonwell cbBTC Lender WETH Borrower
            # "0xd89A4f020C8d256a2A4B0dC40B36Ee0b27680776",  # Moonwell cbETH Lender WETH Borrower
        ],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "explorer": "https://basescan.org/address/",
        "relayer": "0x46679Ba8ce6473a9E0867c52b5A50ff97579740E",
    },
    "arbitrum": {
        "lender_borrowers": [],
        "liquity_lender_borrowers": {},
        "ybold": [
            "0x46Fb8B6431e21959E0975C9F7230bE31baff3AC7",  # yUSND's WETH Strategy
            "0x6B74B94359E1bF07c6E41292Bfd722B3F8f637C7",  # yUSND's wstETH Strategy
            "0xE85D07b2B6fdd3979f802CB161B078212A6eE125",  # yUSND's rETH Strategy
            "0x62B70a5Ef0c2cEEa4a2A85681fd0a9dC398F4439",  # yUSND's ARB Strategy
        ],
        "explorer": "https://arbiscan.io/address/",
        "relayer": "0xE0D19f6b240659da8E87ABbB73446E7B4346Baee",
    },
    "katana": {
        "lender_borrowers": [
            "0x0432337365d89c0D73f1D0Cb263791F8f1B98D43",  # Morpho vbWBTC/yvUSDC Lender Borrower
            "0x3384246D42cAc0B8DD9BBDbE902A06D0814244f7",  # Morpho vbWBTC/yvUSDT Lender Borrower
            "0x2F0b01d1F36FB2c72f7DEB441a2a262e655d6888",  # Morpho vbWETH/yvUSDC Lender Borrower
        ],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "explorer": "https://katanascan.com/address/",
        "relayer": "0xC29cbdcf5843f8550530cc5d627e1dd3007EF231",
    },
}

APR_ORACLE_ADDRESS = "0x1981AD9F44F2EA9aDd2dC4AD7D075c102C70aF92"


def apr_oracle() -> ContractInstance:
    return cast(ContractInstance, Contract(APR_ORACLE_ADDRESS, abi="bot/abis/IAprOracle.json"))


def chain_key() -> str:
    network_name = chain.provider.network.name.lower()
    # Check if it's a custom network (like katana) that exists in our config
    if network_name in NETWORKS:
        return cast(str, network_name)
    # Otherwise fall back to ecosystem name (ethereum, base, arbitrum, etc.)
    return cast(str, chain.provider.network.ecosystem.name.lower())


def cfg() -> NetworkCfg:
    return NETWORKS.get(chain_key(), NETWORKS["ethereum"])


def lender_borrower_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["lender_borrowers"]]


def liquity_lender_borrower_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["liquity_lender_borrowers"].keys()]


def liquity_coll_index(address: str) -> int:
    return cfg()["liquity_lender_borrowers"][address]


def ybold_strategies() -> list[ContractInstance]:
    return [Contract(addr) for addr in cfg()["ybold"]]


def strategies() -> list[ContractInstance]:
    return lender_borrower_strategies() + liquity_lender_borrower_strategies() + ybold_strategies()


def explorer_base_url() -> str:
    return cfg()["explorer"]


def relayer() -> ContractInstance | None:
    addr = cfg()["relayer"]
    if not addr:
        return None
    return cast(ContractInstance, Contract(addr, abi="bot/abis/IRelayer.json"))
