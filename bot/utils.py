import json
import os
import random
from typing import Any, cast

from ape import Contract, accounts
from ape.contracts.base import ContractInstance
from ape.exceptions import ContractLogicError
from ape_accounts import import_account_from_private_key
from ape_ethereum import multicall

from bot.config import EMOJIS, relayer
from bot.tg import notify_group_chat

STATE_FILE = "bot_state.json"
ACCOUNT_ALIAS = "tender"
ACCOUNT_PASSWORD = "42069"

TROVE_STATUS = ["Non Existent", "Active", "Closed By Owner", "Closed By Liquidation", "Zombie"]
DEBT_IN_FRONT_HELPER = "0x4bb5E28FDB12891369b560f2Fab3C032600677c6"
MAX_UINT256 = 2**256 - 1


def load_state() -> dict[str, Any]:
    try:
        with open(STATE_FILE, "r") as f:
            return cast(dict[str, Any], json.load(f))
    except FileNotFoundError:
        return {}


def save_state(state: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def get_signer() -> Any:
    private_key = os.getenv("BOT_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("!BOT_PRIVATE_KEY")

    try:
        account = import_account_from_private_key(ACCOUNT_ALIAS, ACCOUNT_PASSWORD, private_key)
    except Exception:
        account = accounts.load(ACCOUNT_ALIAS)

    account.set_autosign(True, passphrase=ACCOUNT_PASSWORD)
    return account


def execute_tend(strategy_address: str) -> str | None:
    """Execute tend on a strategy via relayer. Returns tx hash on success."""
    try:
        relayer_contract = relayer()
        if not relayer_contract:
            return None
        signer = get_signer()
        receipt = relayer_contract.tendStrategy(strategy_address, sender=signer, required_confirmations=0)
        # weth = Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", abi="bot/abis/IERC20.json")
        # receipt = weth.approve(strategy_address, 0, sender=signer, required_confirmations=0)
        return receipt.txn_hash
    except ContractLogicError as e:
        print(f"execute_tend: {e}")
        return None


def get_signer_balance() -> int:
    """Get the signer's ETH balance in wei."""
    try:
        signer = get_signer()
        return signer.balance
    except Exception:
        return 0


def format_time_ago(seconds: int) -> str:
    """Format seconds into a human-readable time ago string."""
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m ago"
    else:
        return f"{seconds // 86400}d {(seconds % 86400) // 3600}h ago"


async def report_strategy(
    strategy: ContractInstance,
    is_liquity: bool,
    coll_index: int,
    now_ts: int,
    oracle: ContractInstance,
    network: str,
    explorer_url: str,
) -> None:
    """Report status for a single lender borrower strategy."""
    contract = Contract(strategy.address, abi="bot/abis/ILenderBorrower.json")

    # Prepare base multicall
    call = multicall.Call()
    call.add(contract.name)
    call.add(contract.getCurrentLTV)
    call.add(contract.getLiquidateCollateralFactor)
    call.add(contract.targetLTVMultiplier)
    call.add(contract.warningLTVMultiplier)
    call.add(contract.balanceOfDebt)
    call.add(contract.balanceOfLentAssets)
    call.add(contract.lastReport)
    call.add(contract.tendTrigger)
    call.add(contract.asset)
    call.add(contract.borrowToken)

    if is_liquity:
        call.add(contract.troveId)
        call.add(contract.TROVE_MANAGER)

    results = list(call())

    # Unpack base results
    (
        name,
        raw_current_ltv,
        collateral_factor,
        target_ltv_mult,
        warning_ltv_mult,
        balance_of_debt,
        balance_of_lent_assets,
        last_report,
        tend_trigger_result,
        asset_address,
        borrow_token_address,
    ) = results[:11]

    # Get token info
    borrow_token = Contract(borrow_token_address, abi="bot/abis/IERC20.json")
    token_call = multicall.Call()
    token_call.add(borrow_token.decimals)
    token_call.add(borrow_token.symbol)

    # For liquity, also fetch trove data and debt in front
    if is_liquity:
        trove_id, trove_manager_address = results[11], results[12]
        trove_manager = Contract(trove_manager_address, abi="bot/abis/ITroveManager.json")
        debt_helper = Contract(DEBT_IN_FRONT_HELPER, abi="bot/abis/IDebtInFrontHelper.json")
        token_call.add(trove_manager.getLatestTroveData, trove_id)
        token_call.add(trove_manager.getTroveStatus, trove_id)
        token_call.add(debt_helper.getDebtBetweenInterestRateAndTrove, coll_index, 0, MAX_UINT256, trove_id, 0, 0)

    token_results = list(token_call())
    borrow_decimals, borrow_symbol = token_results[0], token_results[1]

    # Calculate values
    debt_formatted = balance_of_debt / (10**borrow_decimals)
    lent_formatted = balance_of_lent_assets / (10**borrow_decimals)
    expected_profit = max(0, lent_formatted - debt_formatted)
    time_str = format_time_ago(now_ts - last_report)
    tend_status = tend_trigger_result[0]
    liquidation_threshold = collateral_factor / 1e16

    # Build message
    msg = (
        f"{random.choice(EMOJIS)} <b>{name}</b>\n\n"
        f"<b>LTV:</b> {raw_current_ltv / 1e16:.1f}%\n"
        f"<b>Target:</b> {liquidation_threshold * target_ltv_mult / 1e4:.1f}%\n"
        f"<b>Warning:</b> {liquidation_threshold * warning_ltv_mult / 1e4:.1f}%\n"
        f"<b>Liquidation:</b> {liquidation_threshold:.1f}%\n"
        f"<b>Expected APR:</b> {int(oracle.getStrategyApr(strategy.address, 0)) / 1e16:.2f}%\n"
    )

    if is_liquity:
        trove_data = token_results[2]
        annual_interest_rate = trove_data[6]  # annualInterestRate is at index 6
        last_rate_adj_time = trove_data[9]  # lastInterestRateAdjTime is at index 9
        trove_status = TROVE_STATUS[token_results[3]]
        debt_in_front = token_results[4][0]  # debt is first element of tuple
        msg += f"\n<b>Trove Status:</b> {trove_status}\n"
        msg += f"<b>Trove Interest Rate:</b> {annual_interest_rate / 1e16:.2f}%\n"
        msg += f"<b>Last Rate Adjustment:</b> {format_time_ago(now_ts - last_rate_adj_time)}\n"
        msg += f"<b>Debt In Front:</b> {debt_in_front / 1e18:,.2f} {borrow_symbol}\n"

    msg += (
        f"\n<b>Amount Borrowed:</b> {debt_formatted:.2f} {borrow_symbol}\n"
        f"<b>Amount in Lender Vault:</b> {lent_formatted:.2f} {borrow_symbol}\n"
        f"<b>Expected Profit:</b> {expected_profit:.2f} {borrow_symbol}\n"
        f"<b>Last Report:</b> {time_str}\n"
        f"<b>Tend Trigger:</b> {tend_status}\n"
        f"<b>Network:</b> {network}\n\n"
        f"<a href='{explorer_url}{strategy.address}'>🔗 View Strategy</a>"
    )

    await notify_group_chat(msg)
