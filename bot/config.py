import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from web3 import Web3
from web3.contract import Contract

# fmt: off
EMOJIS = [
    "🦍", "🐒", "🦧", "🐶", "🐱", "🦁", "🐴", "🦄", "🐮",
    "🐑", "🐫", "🦒", "🐇", "🦔", "🐨", "🦦", "🦩", "🦭", "🐢", "🐳", "🐡",
]
# fmt: on

# =============================================================================
# ABI Loading
# =============================================================================

_ABI_DIR = Path(__file__).parent / "abis"


def load_abi(name: str) -> list[dict[str, Any]]:
    with open(_ABI_DIR / name) as f:
        return json.load(f)  # type: ignore[no-any-return]


BASE_STRATEGY_ABI = load_abi("IBaseStrategy.json")
TOKENIZED_STRATEGY_ABI = load_abi("ITokenizedStrategy.json")
LENDER_BORROWER_ABI = load_abi("ILenderBorrower.json")
ERC20_ABI = load_abi("IERC20.json")
RELAYER_ABI = load_abi("IRelayer.json")
APR_ORACLE_ABI = load_abi("IAprOracle.json")
LENDER_VAULT_ABI = load_abi("ILenderVault.json")
TROVE_MANAGER_ABI = load_abi("ITroveManager.json")
DEBT_IN_FRONT_HELPER_ABI = load_abi("IDebtInFrontHelper.json")
LOOPER_ABI = load_abi("ILooper.json")
MORPHO_ABI = load_abi("IMorpho.json")
MORPHO_IRM_ABI = load_abi("IMorphoIRM.json")
AAVE_DATA_PROVIDER_ABI = load_abi("IAaveDataProvider.json")

# =============================================================================
# Network Configuration
# =============================================================================


class NetworkCfg(TypedDict):
    lender_borrowers: Sequence[str]
    liquity_lender_borrowers: Mapping[str, int]  # address -> collIndex
    ybold: Sequence[str]
    morpho_loopers: Sequence[str]
    aave_loopers: Sequence[str]
    morpho: str  # Morpho singleton address
    explorer: str
    relayer: str | None
    uptime_push_key: str


NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        "lender_borrowers": [
            "0xf6151034BEc135059E5A6Ccff43317652960ad41",  # Curve WETH/crvUSD Lender Borrower
            "0xB3ef10D305A6CdbC5f19244de528d025F856EF6A",  # Curve wstETH/crvUSD Lender Borrower
            "0x5cee43aa4Beb43E114C50d2127b206a6b95F1151",  # Curve WBTC/crvUSD Lender Borrower
            "0xcd89BdDA5D0b93E4c9f96841717D12F26805867F",  # Morpho cbBTC/Sentora RLUSD Lender Borrower
            "0xd1645Ca9666B918dbF4f7aF267A41AccB36B6722",  # Morpho cbBTC/Sentora PYUSD Lender Borrower
            "0xc5976A234574A7345EfcbB3B0AaF5F435355d2DB",  # Morpho OETH/yvUSDC-1 Lender Borrower
            "0x52A52d224573fCBDD6e8353cE1D0591563Fc3Bb4",  # Aave v3 USDC/yvBTC Lender Borrower
            "0x7D3536382805f01b3c8c88a9a2037466C1FEd424",  # Aave v3 cbBTC/yvUSD Lender Borrower
            "0x3a36da4424906752c97532619757E232f4970a0f",  # Aave v3 cbBTC/ysPYUSD Lender Borrower
            "0xCba881a129A8Fe951c5909bDeCe34184B06eCafB",  # Aave v3 cbBTC/ysRLUSD Lender Borrower
            "0x64D67F70Fa1a6898485D69b5916E1ce1e494B026",  # Aave v3 cbBTC/ysUSDT Lender Borrower
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
        "morpho_loopers": [
            "0x03b26cc31A241804a6C79F0d34B2ec4E1E792B68",  # wstETH/WETH Morpho
            "0x5f9DBa2805411a8382FDb4E69d4f2Da8EFaF1F89",  # Infinifi sIUSD Morpho
            "0x7bf1D269bf2CB79E628F51B93763B342fd059D1D",  # stcusd Jul 23 Morpho
            "0xF28DC8B6DeD7E45F8cf84B9972487C8e1857A442",  # syrupusdc/usdc
            "0x0da1f4b3752a163e8c39509b233f2365088e82aA",  # susds/usdt
            "0xE4406F066a790e501ac1658aF2945dbbb2d2E74B",  # lbtc/wbtc
        ],
        "aave_loopers": [
            "0xA0e0B2F2F28A7A9CB16F307582B247240BAc6db0",  # susde/usdt
            "0xddCD9012d00d757C5261f028a20e2943f51A9ed8",  # wstETH/WETH
            "0x2c1280922e7D913404760519e515fFC0B78A0bED",  # Spark wstETH/WETH
            "0xC5E45AE7f641b8f95fcE60EB6ef991EbBd493Ba0",  # Aave v3 auction susde/usdc
        ],
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://etherscan.io/address/",
        "relayer": "0x604e586F17cE106B64185A7a0d2c1Da5bAce711E",
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_ETHEREUM", ""),
    },
    "base": {
        "lender_borrowers": [],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "morpho_loopers": [],
        "aave_loopers": [],
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://basescan.org/address/",
        "relayer": "0x46679Ba8ce6473a9E0867c52b5A50ff97579740E",
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_BASE", ""),
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
        "morpho_loopers": [
            "0xBCf08997C34183d1b7B0f99e13aCeACFBA88E453",  # syrup/usdc
        ],
        "aave_loopers": [],
        "morpho": "0x6c247b1F6182318877311737BaC0844bAa518F5e",
        "explorer": "https://arbiscan.io/address/",
        "relayer": "0xE0D19f6b240659da8E87ABbB73446E7B4346Baee",
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_ARBITRUM", ""),
    },
    "katana": {
        "lender_borrowers": [
            "0x0432337365d89c0D73f1D0Cb263791F8f1B98D43",  # Morpho vbWBTC/yvUSDC Lender Borrower
            "0x3384246D42cAc0B8DD9BBDbE902A06D0814244f7",  # Morpho vbWBTC/yvUSDT Lender Borrower
            "0x2F0b01d1F36FB2c72f7DEB441a2a262e655d6888",  # Morpho vbWETH/yvUSDC Lender Borrower
        ],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "morpho_loopers": [],
        "aave_loopers": [],
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://katanascan.com/address/",
        "relayer": "0xC29cbdcf5843f8550530cc5d627e1dd3007EF231",
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_KATANA", ""),
    },
}

NETWORK_RPC_ENVS: Mapping[str, str] = {
    "ethereum": "ETH_RPC_URL",
    "base": "BASE_RPC_URL",
    "arbitrum": "ARB_RPC_URL",
    "katana": "KATANA_RPC_URL",
}

APR_ORACLE_ADDRESS = "0x1981AD9F44F2EA9aDd2dC4AD7D075c102C70aF92"


# =============================================================================
# Helpers
# =============================================================================


def network() -> str:
    return os.getenv("NETWORK", "ethereum")


def cfg() -> NetworkCfg:
    return NETWORKS.get(network(), NETWORKS["ethereum"])


def explorer_base_url() -> str:
    return cfg()["explorer"]


def uptime_push_url() -> str | None:
    host = os.getenv("UPTIME_KUMA_HOST", "")
    key = cfg()["uptime_push_key"]
    if not host or not key:
        return None
    return f"https://{host}/api/push/{key}?status=up&msg=OK&ping="


def w3_contract(w3: Web3, address: str, abi: list[dict[str, Any]]) -> Contract:
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def all_strategy_addrs() -> list[str]:
    c = cfg()
    return (
        list(c["lender_borrowers"])
        + list(c["liquity_lender_borrowers"].keys())
        + list(c["ybold"])
        + list(c["morpho_loopers"])
        + list(c["aave_loopers"])
    )


def lender_borrower_addrs() -> list[str]:
    return list(cfg()["lender_borrowers"])


def liquity_lender_borrower_map() -> dict[str, int]:
    return dict(cfg()["liquity_lender_borrowers"])


def morpho_looper_addrs() -> list[str]:
    return list(cfg()["morpho_loopers"])


def aave_looper_addrs() -> list[str]:
    return list(cfg()["aave_loopers"])


def all_looper_addrs() -> list[str]:
    return morpho_looper_addrs() + aave_looper_addrs()


def morpho_address() -> str:
    return cfg()["morpho"]


def liquity_coll_index(address: str) -> int:
    return cfg()["liquity_lender_borrowers"][address]


def ybold_addrs() -> list[str]:
    return list(cfg()["ybold"])


def apr_oracle(w3: Web3) -> Contract:
    return w3_contract(w3, APR_ORACLE_ADDRESS, APR_ORACLE_ABI)


def relayer(w3: Web3) -> Contract | None:
    addr = cfg()["relayer"]
    if not addr:
        return None
    return w3_contract(w3, addr, RELAYER_ABI)
