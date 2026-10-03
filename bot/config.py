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
PAWN_BROKER_ABI = load_abi("IPawnBroker.json")
MORPHO_ABI = load_abi("IMorpho.json")
MORPHO_IRM_ABI = load_abi("IMorphoIRM.json")
AAVE_DATA_PROVIDER_ABI = load_abi("IAaveDataProvider.json")
REGISTRY_ABI = load_abi("IRegistry.json")
VAULT_ABI = load_abi("IVault.json")
COMMON_REPORT_TRIGGER_ABI = load_abi("ICommonReportTrigger.json")
DEBT_ALLOCATOR_ABI = load_abi("IDebtAllocator.json")
ROLE_MANAGER_ABI = load_abi("IRoleManager.json")
PERMISSIONLESS_RELAYER_ABI = load_abi("IPermissionlessRelayer.json")

# Yearn v3 registries (same address on all chains)
REGISTRY_ADDRESSES = [
    "0xd40ecF29e001c76Dcc4cC0D9cd50520CE845B038",
    "0xff31A1B020c868F6eA3f61Eb953344920EeCA3af",
]
MULTI_STRATEGY_VAULT_TYPE = 1

# =============================================================================
# Network Configuration
# =============================================================================


class NetworkCfg(TypedDict):
    lender_borrowers: Sequence[str]
    liquity_lender_borrowers: Mapping[str, int]  # address -> collIndex
    ybold: Sequence[str]
    morpho_loopers: Sequence[str]
    aave_loopers: Sequence[str]
    flex_loopers: Sequence[str]
    pawnbroker_loopers: Sequence[str]
    allocator_vaults: Sequence[str]  # Yearn v3 allocator vaults to broadcast deposit/withdraw/report events for
    keepers: Mapping[str, str]  # keeper EOA -> label; gas balance is monitored alongside our signers
    morpho: str  # Morpho singleton address
    explorer: str
    relayers: Sequence[str]  # TKSRelayers our signers act through
    keeper_interval: int  # seconds between keeper sweeps
    keeper_include: Sequence[str]  # vaults/strategies to keep that aren't endorsed in the registries
    keeper_skip: Sequence[str]  # vaults/strategies the keeper never touches
    keeper_extra_strategies: Mapping[str, Sequence[str]]  # vault -> strategies outside its default queue
    uptime_push_key: str


NETWORKS: Mapping[str, NetworkCfg] = {
    "ethereum": {
        "lender_borrowers": [
            "0xfd2E20643CE740F0FE72ebC0328747bb415cf055",  # Aave v3 wstETH/yvUSD Lender Borrower
            "0x5b53539965a3224A7197DF30bD5a75a4F779e479",  # Aave v3 WETH/yvUSD Lender Borrower
            "0x41cfE42D221a591C6308Dcea419015Ba8570B380",  # Spark wstETH/yvUSD Lender Borrower
            "0x5E8A9Acd00AdCED69b30D36929CbF7D4d4F9AE1F",  # Spark WETH/yvUSD Lender Borrower
            "0xc7B499ce6b3ae65e5CBC077ab3f3CEE155CcC0F8",  # Morpho wstETH/yvUSD
            "0x7079874f4659f8a093Daac6035b6c87383529B40",  # Morpho WETH/yvUSD
            # "0xf6151034BEc135059E5A6Ccff43317652960ad41",  # Curve WETH/crvUSD Lender Borrower
            # "0xB3ef10D305A6CdbC5f19244de528d025F856EF6A",  # Curve wstETH/crvUSD Lender Borrower
            # "0x5cee43aa4Beb43E114C50d2127b206a6b95F1151",  # Curve WBTC/crvUSD Lender Borrower
            # "0xcd89BdDA5D0b93E4c9f96841717D12F26805867F",  # Morpho cbBTC/Sentora RLUSD Lender Borrower
            # "0xd1645Ca9666B918dbF4f7aF267A41AccB36B6722",  # Morpho cbBTC/Sentora PYUSD Lender Borrower
            # "0xc5976A234574A7345EfcbB3B0AaF5F435355d2DB",  # Morpho OETH/yvUSDC-1 Lender Borrower
            # "0x52A52d224573fCBDD6e8353cE1D0591563Fc3Bb4",  # Aave v3 USDC/yvBTC Lender Borrower
            # "0x7D3536382805f01b3c8c88a9a2037466C1FEd424",  # Aave v3 cbBTC/yvUSD Lender Borrower
            # "0x3a36da4424906752c97532619757E232f4970a0f",  # Aave v3 cbBTC/ysPYUSD Lender Borrower
            # "0xCba881a129A8Fe951c5909bDeCe34184B06eCafB",  # Aave v3 cbBTC/ysRLUSD Lender Borrower
            # "0x64D67F70Fa1a6898485D69b5916E1ce1e494B026",  # Aave v3 cbBTC/ysUSDT Lender Borrower
        ],
        "liquity_lender_borrowers": {
            # "0x2fFff76ee152164f4dEfc95fB0cf88528251aB9E": 2,  # Liquity rETH/BOLD Lender Borrower (collIndex=2)
        },
        "ybold": [
            "0x2048A730f564246411415f719198d6f7c10A7961",  # yBOLD's WETH Strategy
            "0x46af61661B1e15DA5bFE40756495b7881F426214",  # yBOLD's wstETH Strategy
            "0x2351E217269A4a53a392bffE8195Efa1c502A1D2",  # yBOLD's rETH Strategy
            # "0xad7D5D31Ffcb96f6F719Bb78209019d3d09e6baa",  # sUSDaf's ysyBOLD Strategy
            # "0xF6516d45A1625a6d9d3479902a5CB4c8B79F1887",  # sUSDaf's sUSDS Strategy
            # "0x388095a341Bf5767d3d3B7093cd89A82B816B507",  # sUSDaf's sfrxETH Strategy
            # "0xb00a77045574f42b9Aff25dB275af4d5d25146bb",  # sUSDaf's tBTC Strategy
            # "0x1d53B127629AF8df7da5488833a50c2F12692F5C",  # sUSDaf's WBTC18 Strategy
        ],
        "morpho_loopers": [
            # "0x03b26cc31A241804a6C79F0d34B2ec4E1E792B68",  # wstETH/WETH Morpho
            "0x5f9DBa2805411a8382FDb4E69d4f2Da8EFaF1F89",  # Infinifi sIUSD Morpho
            "0x7bf1D269bf2CB79E628F51B93763B342fd059D1D",  # stcusd Jul 23 Morpho
            "0xF28DC8B6DeD7E45F8cf84B9972487C8e1857A442",  # syrupusdc/usdc
            "0x0da1f4b3752a163e8c39509b233f2365088e82aA",  # susds/usdt
            "0xE4406F066a790e501ac1658aF2945dbbb2d2E74B",  # lbtc/wbtc
            "0x8C8232Bdffc60BAb474CABa0245e63726e85Ce15",  # wOUSD/USDC
            "0xF0FEC2602Dff25497D6a14b3113D0687b4c56741",  # siUSD/USDC
        ],
        "aave_loopers": [
            # "0xA0e0B2F2F28A7A9CB16F307582B247240BAc6db0",  # susde/usdt
            # "0xddCD9012d00d757C5261f028a20e2943f51A9ed8",  # wstETH/WETH
            "0x2c1280922e7D913404760519e515fFC0B78A0bED",  # Spark wstETH/WETH
            # "0xC5E45AE7f641b8f95fcE60EB6ef991EbBd493Ba0",  # Aave v3 auction susde/usdc
            "0x68A14629cb07c74259f481382fE8b6cFD8970121",  # wstETH/WETH spark v3
        ],
        "flex_loopers": [
            "0x255f538312331e2921387Ea18D901c84a9614f90",  # yvUSD/USDC Flex Looper
        ],
        "pawnbroker_loopers": [
            "0xd362efC75Ef1879f37A900823495f402CfdB0986",  # stcUSD/USDC Pawn Broker Looper
        ],
        "allocator_vaults": [
            "0x863687e4E9751b57F38b4B0ebA04744C72d0f7B8",  # yvFlexUSDC
            "0xfaC55fAFD0b55BFb8dD41F735EfCc195adA9891F",  # yvFlexWETH
        ],
        "keepers": {
            "0x283132390eA87D6ecc20255B59Ba94329eE17961": "TKS keeper",
        },
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://etherscan.io/address/",
        "relayers": [
            "0x604e586F17cE106B64185A7a0d2c1Da5bAce711E",
            "0xc2d26d13582324f10c7c3753B8F5Fc71011EcF57",
        ],
        "keeper_interval": 557,
        "keeper_include": [
            "0x23346B04a7f55b8760E5860AA5A77383D63491cD",  # staked yBold
            "0xAaaFEa48472f77563961Cdb53291DEDfB46F9040",  # Locked yvUSD
            "0x6dec370EfA894d48D8C55012B0Cd6f3C1C7C4616",  # Asymmetry tBTC Lender USDaf Borrower
            "0xB3ef10D305A6CdbC5f19244de528d025F856EF6A",  # Curve wstETH/crvUSD Lender Borrower
            "0x68D01e2915c39b85EFE691dbb87bF93C6194A4a0",  # Morpho WBTC/yvUSD Lender Borrower
            "0x9da810867E4AA706e02318Bf7869f8530af663ad",  # Morpho WBTC/yvUSDT-1 Lender Borrower
            "0xc5976A234574A7345EfcbB3B0AaF5F435355d2DB",  # Morpho OETH/yvUSDC-1 Lender Borrower
        ],
        "keeper_skip": [
            "0x564F7b5d8389F5C4c99E50fED5fC95070e697903",  # PendleLPCompounder
            "0xb6da41D4BDb484BDaD0BfAa79bC8E182E5095F7e",  # Morpho Usual Boosted USDC Compounder
            "0x503e0BaB6acDAE73eA7fb7cf6Ae5792014dbe935",  # ajna-weth
            "0xe24BA27551aBE96Ca401D39761cA2319Ea14e3CB",  # ajna-dai
            "0xf1ce36c9C0dB95A052Eb4b075BC334e1f5a21Ef0",  # yPT-rswETH
            "0x66017371c032Cd5a67Fec6913A9e37d5bd1C690c",  # yPT-pufETH
            "0xE403bbF2262643c2e996E7469be736E211D5B272",  # yPT-ezETH
            "0x2F2BBc50DB252eeADD2c9B9197beb6e5Aef87e48",  # yPT-ENA
            "0xDDa02A2FA0bb0ee45Ba9179a3fd7e65E5D3B2C90",  # yPT-agETH
            "0xebF3581407ae0Ceb07B8149b4C3AC995a72cb589",  # yPT-wstETH
            "0x57a8b4061AA598d2Bb5f70C5F931a75C9F511fc8",  # yPT-LBTC
            "0xdc0B53cC326B692a4D89e5F4CadC29a6B7265749",  # yPT-rswETH-L2
            "0x8F6695aaCCEb1675Ad38Ff529e5FbAEBd76942e1",  # some ptBS
            "0x3927C4AD1D63BF9629fDaE1318aa31DF9135F544",  # ajna thingy
            "0x43CCaD774B20de2cf920531529a7b7cc5a23F887",  # another ajna thingy
            "0x288991C055F94E9A0dcF0Ad08Ee3496E96E68142",  # steth acc
            "0xE82D060687C014B280b65df24AcD94A77251C784",  # sUSDS we need to rate limit
            "0x91F008870eEF686b61a3775944D55a3FC53B7024",  # old ssr USDS
            "0x459F99D7c83Bc3653b1913B62D2978b1deDa01B5",  # sUSDC
            "0x8A878E3149051B810F078FD3F2E0924290be34A6",  # pendle
            "0x9C0A49b11389FA5AdC6304dc694AB115B33F7bA7",  # pendle
            "0x4Dd0FE8549641A04d7ab4f37dbb541aE7dBb2838",  # pendle
            "0x4A0Fce1af23BB0d6C63A67A9658728d34e37ec00",  # pendle
            "0x48c03B6FfD0008460F8657Db1037C7e09dEedfcb",  # katana
            "0x7B5A0182E400b241b317e781a4e9dEdFc1429822",  # katana
            "0x92C82f5F771F6A44CfA09357DD0575B81BF5F728",  # katana
            "0xcc6a16Be713f6a714f68b0E1f4914fD3db15fBeF",  # katana
            "0xF470EB50B4a60c9b069F7Fd6032532B8F5cC014d",  # katana
            "0xA5DaB32DbE68E6fa784e1e50e4f620a0477D3896",  # katana
            "0xe1Ac97e2616Ad80f69f705ff007A4bbb3655544a",  # katana
            "0x77570CfEcf83bc6bB08E2cD9e8537aeA9F97eA2F",  # katana
            "0x5cee43aa4Beb43E114C50d2127b206a6b95F1151",  # Curve WBTC/crvUSD Lender Borrower
            "0xf6151034BEc135059E5A6Ccff43317652960ad41",  # Curve WETH/crvUSD Lender Borrower
            "0x2fFff76ee152164f4dEfc95fB0cf88528251aB9E",  # Liquity rETH/BOLD Lender Borrower
            "0x268350b21732D47F6b1e4A45Cc67F30820175c9a",  # USDaf WBTC18 Stability Pool
            "0xEcf4dCBb6Aba1925a77038914E406037011B676F",  # USDaf sUSDS Stability Pool
            "0x6fdF47fb4198677D5B0843e52Cf12B5464cE723E",  # Curve WETH Lender crvUSD Borrower
            "0x696d02Db93291651ED510704c9b286841d506987",  # yvUSD
        ],
        "keeper_extra_strategies": {
            "0xBF319dDC2Edc1Eb6FDf9910E39b37Be221C8805F": [  # yvcrvUSD-2
                "0x279C50b6895126BBbcF9d2ED7c3FB59bdc8a18dF",  # sDOLA Curve
                "0x6AbBda8243F4BF130a97beae759A6e91522520b9",  # sUSDe Curve
                "0xf91a9A1C782a1C11B627f6E576d92C7d72CDd4AF",  # sfrxUSD Curve
                "0x2d2C784f45D9FCCE8a5bF9ebf4ee01FA6f064D1D",  # USDe Curve
                "0x75b7DB3e11138134fe4744553b5e5e3D6546d289",  # sDOLA Convex
                "0x6C2C45429b76406b3aAbB37b829F0B57C7badbBe",  # sUSDe Convex
                "0x7A26C6c1628c86788526eFB81f37a2ffac243A98",  # sfrxUSD Convex
                "0x4058dec53A72f97327dE7dD406C7E2dFD19F9a86",  # USDe Convex
                "0xBaadd4b44929606178FcDBd2f4309282f39D9dA7",  # sreUSD Convex
                "0x6c7150b9eb23eE563b28905791aD5B6C9cB6B21a",  # fxSAVE Convex
            ],
        },
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_ETHEREUM", ""),
    },
    "base": {
        "lender_borrowers": [],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "morpho_loopers": [],
        "aave_loopers": [],
        "flex_loopers": [],
        "pawnbroker_loopers": [],
        "allocator_vaults": [],
        "keepers": {
            "0x283132390eA87D6ecc20255B59Ba94329eE17961": "TKS keeper",
        },
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://basescan.org/address/",
        "relayers": [
            "0x46679Ba8ce6473a9E0867c52b5A50ff97579740E",
        ],
        "keeper_interval": 600,
        "keeper_include": [],
        "keeper_skip": [],
        "keeper_extra_strategies": {},
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
        "flex_loopers": [],
        "pawnbroker_loopers": [],
        "allocator_vaults": [],
        "keepers": {
            "0x283132390eA87D6ecc20255B59Ba94329eE17961": "TKS keeper",
        },
        "morpho": "0x6c247b1F6182318877311737BaC0844bAa518F5e",
        "explorer": "https://arbiscan.io/address/",
        "relayers": [
            "0xE0D19f6b240659da8E87ABbB73446E7B4346Baee",
        ],
        "keeper_interval": 600,
        "keeper_include": [
            # "0xaDa882B1BcB9B658b354ade0cE64586A88cb6849",  # cctp remote MorphoCompounder
            "0x78b7774c4368df8f2c115Abf6210F557753a6aC5",  # MorphoCompounder
        ],
        "keeper_skip": [
            "0x8B25CFbAC2aC634071CbcCb20F298b176fd86007",  # yPT healthcheck failing
            "0xC40DA6a01Ac36F39736731ee50fb3b1B8204e2D3",  # pendle
            "0x571293fD9d9716D50ba48Aa1628840D7FA166B20",  # pendle
            "0x1Dd930ADD968ff5913C3627dAA1e6e6FCC9dc544",  # pendle
            "0x62a6d4B860f43D1e52529e21C9C74dDfeAaFC168",  # pendle
            "0x08e3D13d50310aFbeA2da20A3DBD92aAcFc503Ac",  # pendle
            "0x044E75fCbF7BD3f8f4577FF317554e9c0037F145",  # pendle
            "0xE43C0bbbfC34575927798B8Ba9d58AE58F2Be3C6",  # pendle
        ],
        "keeper_extra_strategies": {},
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_ARBITRUM", ""),
    },
    "katana": {
        "lender_borrowers": [
            # "0x0432337365d89c0D73f1D0Cb263791F8f1B98D43",  # Morpho vbWBTC/yvUSDC Lender Borrower
            "0x3384246D42cAc0B8DD9BBDbE902A06D0814244f7",  # Morpho vbWBTC/yvUSDT Lender Borrower
            # "0x2F0b01d1F36FB2c72f7DEB441a2a262e655d6888",  # Morpho vbWETH/yvUSDC Lender Borrower
            "0x0432337365d89c0D73f1D0Cb263791F8f1B98D43",  # Morpho vbWBTC/yvUSDC Lender Borrower
        ],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "morpho_loopers": [],
        "aave_loopers": [],
        "flex_loopers": [],
        "pawnbroker_loopers": [],
        "allocator_vaults": [],
        "keepers": {
            "0x283132390eA87D6ecc20255B59Ba94329eE17961": "TKS keeper",
        },
        "morpho": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        "explorer": "https://katanascan.com/address/",
        "relayers": [
            "0xC29cbdcf5843f8550530cc5d627e1dd3007EF231",
        ],
        "keeper_interval": 3602,
        "keeper_include": [
            "0x0432337365d89c0D73f1D0Cb263791F8f1B98D43",  # Morpho vbWBTC/yvUSDC Lender Borrower
            "0x3384246D42cAc0B8DD9BBDbE902A06D0814244f7",  # Morpho vbWBTC/yvUSDT Lender Borrower
            "0x2F0b01d1F36FB2c72f7DEB441a2a262e655d6888",  # Morpho vbWETH/yvUSDC Lender Borrower
        ],
        "keeper_skip": [],
        "keeper_extra_strategies": {},
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_KATANA", ""),
    },
    "optimism": {
        "lender_borrowers": [],
        "liquity_lender_borrowers": {},
        "ybold": [],
        "morpho_loopers": [],
        "aave_loopers": [],
        "flex_loopers": [],
        "pawnbroker_loopers": [],
        "allocator_vaults": [],
        "keepers": {
            "0x283132390eA87D6ecc20255B59Ba94329eE17961": "TKS keeper",
        },
        "morpho": "",
        "explorer": "https://optimistic.etherscan.io/address/",
        "relayers": [
            "0x21BB199ab3be9E65B1E60b51ea9b0FE9a96a480a",
        ],
        "keeper_interval": 600,
        "keeper_include": [
            "0x81bDd5E8FbDE5A85A2D38761D03d2307FE69A329",  # Aave V3 USDC.e Lender
            "0x91e6C36992380017aECc91b0c21b0fBf4Bb4fdd6",  # Aave V3 DAI Lender
            "0x1b158F71258C06d194Fa2EccFA09e973DE93BB2c",  # Aave V3 USDT Lender
            "0xb3F14E3fda2147fa7574fd003BA40Df266E0B90c",  # Aave V3 WETH Lender
            "0x28911D98AeeC53254631a5aEC3588ea0ADd855C4",  # Aave V3 OP Lender
        ],
        "keeper_skip": [],
        "keeper_extra_strategies": {},
        "uptime_push_key": os.getenv("UPTIME_KUMA_KEY_OPTIMISM", ""),
    },
}

NETWORK_RPC_ENVS: Mapping[str, str] = {
    "ethereum": "ETH_RPC_URL",
    "base": "BASE_RPC_URL",
    "arbitrum": "ARB_RPC_URL",
    "katana": "KATANA_RPC_URL",
    "optimism": "OP_RPC_URL",
}

APR_ORACLE_ADDRESS = "0x1981AD9F44F2EA9aDd2dC4AD7D075c102C70aF92"

# Keeper contracts (same address on all chains)
PERMISSIONLESS_RELAYER = "0x52605BbF54845f520a3E94792d019f62407db2f8"
COMMON_REPORT_TRIGGER = "0xf8dF17a35c88AbB25e83C92f9D293B4368b9D52D"

FLASHBOTS_RPC = "https://rpc.flashbots.net/fast"


# =============================================================================
# Helpers
# =============================================================================


def network() -> str:
    return os.getenv("NETWORK", "ethereum")


def cfg() -> NetworkCfg:
    return NETWORKS.get(network(), NETWORKS["ethereum"])


def explorer_base_url() -> str:
    return cfg()["explorer"]


def private_rpc_url() -> str:
    return os.getenv("PRIVATE_RPC_URL", FLASHBOTS_RPC if network() == "ethereum" else "")


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
        + list(c["flex_loopers"])
        + list(c["pawnbroker_loopers"])
    )


def lender_borrower_addrs() -> list[str]:
    return list(cfg()["lender_borrowers"])


def liquity_lender_borrower_map() -> dict[str, int]:
    return dict(cfg()["liquity_lender_borrowers"])


def morpho_looper_addrs() -> list[str]:
    return list(cfg()["morpho_loopers"])


def aave_looper_addrs() -> list[str]:
    return list(cfg()["aave_loopers"])


def flex_looper_addrs() -> list[str]:
    return list(cfg()["flex_loopers"])


def pawnbroker_looper_addrs() -> list[str]:
    return list(cfg()["pawnbroker_loopers"])


def all_looper_addrs() -> list[str]:
    return morpho_looper_addrs() + aave_looper_addrs() + flex_looper_addrs() + pawnbroker_looper_addrs()


def allocator_vault_addrs() -> list[str]:
    return list(cfg()["allocator_vaults"])


def keeper_map() -> dict[str, str]:
    return dict(cfg()["keepers"])


def morpho_address() -> str:
    return cfg()["morpho"]


def liquity_coll_index(address: str) -> int:
    return cfg()["liquity_lender_borrowers"][address]


def ybold_addrs() -> list[str]:
    return list(cfg()["ybold"])


def apr_oracle(w3: Web3) -> Contract:
    return w3_contract(w3, APR_ORACLE_ADDRESS, APR_ORACLE_ABI)


def relayer_addrs() -> list[str]:
    return list(cfg()["relayers"])


def keeper_interval() -> int:
    return cfg()["keeper_interval"]


def keeper_include_addrs() -> list[str]:
    return list(cfg()["keeper_include"])


def keeper_skip_addrs() -> list[str]:
    return list(cfg()["keeper_skip"])


def keeper_extra_strategies(vault: str) -> list[str]:
    return list(cfg()["keeper_extra_strategies"].get(vault, []))
