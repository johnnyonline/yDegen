import os
import random
import time
from urllib.request import Request, urlopen

from tinybot import TinyBot, multicall, notify_group_chat
from web3 import Web3

from bot.config import (
    APR_ORACLE_ABI,
    APR_ORACLE_ADDRESS,
    BASE_STRATEGY_ABI,
    DEBT_IN_FRONT_HELPER_ABI,
    EMOJIS,
    ERC20_ABI,
    LENDER_BORROWER_ABI,
    LENDER_VAULT_ABI,
    RELAYER_ABI,
    TOKENIZED_STRATEGY_ABI,
    TROVE_MANAGER_ABI,
    all_strategy_addrs,
    cfg,
    explorer_base_url,
    lender_borrower_addrs,
    liquity_lender_borrower_map,
    network,
    uptime_push_url,
    w3_contract,
)
from bot.utils import format_time_ago, load_state, save_state

# =============================================================================
# Constants
# =============================================================================

TEND_CHECK_INTERVAL = int(os.getenv("TEND_CHECK_INTERVAL", "60"))  # 60 seconds default
STATUS_REPORT_CRON = os.getenv("STATUS_REPORT_CRON", "0 8 * * *")  # Daily at 8 AM UTC
ALERT_COOLDOWN_SECONDS = int(os.getenv("TEND_TRIGGER_ALERT_COOLDOWN_SECONDS", "600"))  # 10 minutes default
MIN_SIGNER_BALANCE = int(os.getenv("MIN_SIGNER_BALANCE", str(5 * 10**16)))  # 0.05 ETH default
BALANCE_CHECK_INTERVAL = int(os.getenv("BALANCE_CHECK_INTERVAL", "18000"))  # 5 hours default
UPTIME_PING_INTERVAL = int(os.getenv("UPTIME_PING_INTERVAL", "540"))  # 9 minutes default

DEBT_IN_FRONT_HELPER = "0x4bb5E28FDB12891369b560f2Fab3C032600677c6"
MAX_UINT256 = 2**256 - 1
TROVE_STATUS = ["Non Existent", "Active", "Closed By Owner", "Closed By Liquidation", "Zombie"]

# Track pending tends: strategy_address -> nonce used
_pending_tends: dict[str, int] = {}


# =============================================================================
# Tend Trigger Monitoring
# =============================================================================


async def check_tend_triggers(bot: TinyBot) -> None:
    strategy_addrs = all_strategy_addrs()
    if not strategy_addrs:
        return

    w3 = bot.w3
    calls = [w3_contract(w3, addr, BASE_STRATEGY_ABI).functions.tendTrigger() for addr in strategy_addrs]
    results = multicall(w3, calls)

    now_ts = int(time.time())
    net = network().capitalize()

    for addr, (needs_tend, _data) in zip(strategy_addrs, results):
        if not needs_tend:
            continue

        # Check cooldown
        state = load_state()
        last_ts = state.get("tend_alerts_ts", {}).get(addr, 0)
        if now_ts - last_ts < ALERT_COOLDOWN_SECONDS:
            continue

        strategy_name = w3_contract(w3, addr, TOKENIZED_STRATEGY_ABI).functions.name().call()

        # Update cooldown
        state.setdefault("tend_alerts_ts", {})[addr] = now_ts
        save_state(state)

        await notify_group_chat(
            f"🚨 <b>Strategy needs tending!</b>\n\n"
            f"<b>Name:</b> {strategy_name}\n"
            f"<b>Network:</b> {net}\n\n"
            f"<i>Attempting to tend...</i>\n"
            f"<i>Sleeping for {int(ALERT_COOLDOWN_SECONDS / 60)} minutes...</i>\n\n"
            f"<a href='{explorer_base_url()}{addr}'>🔗 View Strategy</a>"
        )

        await execute_tend(bot, addr, strategy_name, net)


async def execute_tend(bot: TinyBot, strategy_address: str, strategy_name: str, network_name: str) -> None:
    if not bot.executor:
        return

    relayer_addr = cfg()["relayer"]
    if not relayer_addr:
        return

    # Skip if a tend tx for this strategy is still pending
    if strategy_address in _pending_tends:
        pending_nonce = _pending_tends[strategy_address]
        current_nonce = bot.w3.eth.get_transaction_count(bot.executor.address)
        if current_nonce <= pending_nonce:
            return  # Previous tx still pending
        del _pending_tends[strategy_address]  # Previous tx confirmed, clear it

    # Track the nonce we're about to use
    nonce = bot.w3.eth.get_transaction_count(bot.executor.address)
    _pending_tends[strategy_address] = nonce

    relayer_contract = w3_contract(bot.w3, relayer_addr, RELAYER_ABI)
    call = relayer_contract.functions.tendStrategy(Web3.to_checksum_address(strategy_address))
    tx_hash = bot.executor.execute(call, max_priority_fee_gwei=3, wait=0)

    explorer_tx = explorer_base_url().replace("/address/", "/tx/")
    await notify_group_chat(
        f"✅ <b>Tend tx submitted</b>\n\n"
        f"<b>Name:</b> {strategy_name}\n"
        f"<b>Network:</b> {network_name}\n\n"
        f"<a href='{explorer_tx}{tx_hash}'>🔗 View Transaction</a>"
    )


# =============================================================================
# Status Report
# =============================================================================


async def report_status(bot: TinyBot) -> None:
    w3 = bot.w3
    regular_addrs = lender_borrower_addrs()
    liquity_map = liquity_lender_borrower_map()
    liquity_addrs_set = set(liquity_map.keys())
    all_addrs = regular_addrs + list(liquity_map.keys())

    if not all_addrs:
        return

    now_ts = int(time.time())
    net = network().capitalize()
    explorer_url = explorer_base_url()
    oracle = w3_contract(w3, APR_ORACLE_ADDRESS, APR_ORACLE_ABI)

    for addr in all_addrs:
        is_liquity = addr in liquity_addrs_set
        coll_index = liquity_map.get(addr, 0)
        await report_strategy(w3, addr, is_liquity, coll_index, now_ts, oracle, net, explorer_url)


async def report_strategy(
    w3: Web3,
    address: str,
    is_liquity: bool,
    coll_index: int,
    now_ts: int,
    oracle: object,
    network_name: str,
    explorer_url: str,
) -> None:
    addr = Web3.to_checksum_address(address)
    contract = w3_contract(w3, address, LENDER_BORROWER_ABI)
    strategy = w3_contract(w3, address, TOKENIZED_STRATEGY_ABI)

    # Prepare base multicall
    calls = [
        strategy.functions.totalAssets(),
        contract.functions.name(),
        contract.functions.getCurrentLTV(),
        contract.functions.getLiquidateCollateralFactor(),
        contract.functions.targetLTVMultiplier(),
        contract.functions.warningLTVMultiplier(),
        contract.functions.balanceOfDebt(),
        contract.functions.balanceOfLentAssets(),
        contract.functions.lastReport(),
        contract.functions.tendTrigger(),
        contract.functions.asset(),
        contract.functions.borrowToken(),
    ]

    if not is_liquity:
        calls.append(contract.functions.lenderVault())

    if is_liquity:
        calls.append(contract.functions.troveId())
        calls.append(contract.functions.TROVE_MANAGER())

    results = multicall(w3, calls)

    # Skip if no assets
    total_assets = results[0]
    if total_assets == 0:
        return

    # Unpack base results
    (
        _,
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
    ) = results[:12]

    # Second multicall: token info + APR + conditional data
    borrow_token = w3_contract(w3, borrow_token_address, ERC20_ABI)
    calls2 = [
        borrow_token.functions.decimals(),
        borrow_token.functions.symbol(),
        oracle.functions.getStrategyApr(addr, 0),
    ]

    # For non-liquity, fetch lender vault max withdraw
    if not is_liquity:
        lender_vault_address = results[12]
        lender_vault = w3_contract(w3, lender_vault_address, LENDER_VAULT_ABI)
        calls2.append(lender_vault.functions.maxWithdraw(addr))

    # For liquity, fetch trove data and debt in front via direct calls (tuple returns not supported by multicall)
    if is_liquity:
        trove_id, trove_manager_address = results[12], results[13]
        trove_manager = w3_contract(w3, trove_manager_address, TROVE_MANAGER_ABI)
        debt_helper = w3_contract(w3, DEBT_IN_FRONT_HELPER, DEBT_IN_FRONT_HELPER_ABI)

    token_results = multicall(w3, calls2)
    borrow_decimals, borrow_symbol = token_results[0], token_results[1]
    expected_apr = token_results[2] / 1e16

    # Calculate values
    debt_formatted = balance_of_debt / (10**borrow_decimals)
    lent_formatted = balance_of_lent_assets / (10**borrow_decimals)

    if not is_liquity:
        lender_max_withdraw = token_results[3]
        max_withdraw_formatted = lender_max_withdraw / (10**borrow_decimals)
        max_withdraw_pct = (lender_max_withdraw / balance_of_lent_assets * 100) if balance_of_lent_assets > 0 else 0.0

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
        f"<b>Expected APR:</b> {expected_apr:.2f}%\n"
    )

    if is_liquity:
        trove_data = trove_manager.functions.getLatestTroveData(trove_id).call()
        annual_interest_rate = trove_data[6]  # annualInterestRate is at index 6
        last_rate_adj_time = trove_data[9]  # lastInterestRateAdjTime is at index 9
        trove_status_raw = trove_manager.functions.getTroveStatus(trove_id).call()
        trove_status = TROVE_STATUS[trove_status_raw]
        debt_result = debt_helper.functions.getDebtBetweenInterestRateAndTrove(
            coll_index, 0, MAX_UINT256, trove_id, 0, 0
        ).call()
        debt_in_front = debt_result[0]
        msg += f"\n<b>Trove Status:</b> {trove_status}\n"
        msg += f"<b>Trove Interest Rate:</b> {annual_interest_rate / 1e16:.2f}%\n"
        msg += f"<b>Last Rate Adjustment:</b> {format_time_ago(now_ts - last_rate_adj_time)}\n"
        msg += f"<b>Debt In Front:</b> {debt_in_front / 1e18:,.2f} {borrow_symbol}\n"

    msg += (
        f"\n<b>Amount Borrowed:</b> {debt_formatted:.2f} {borrow_symbol}\n"
        f"<b>Amount in Lender Vault:</b> {lent_formatted:.2f} {borrow_symbol}\n"
        f"<b>Expected Profit:</b> {expected_profit:.2f} {borrow_symbol}\n"
    )

    if not is_liquity:
        msg += f"<b>Lender Max Withdraw:</b> {max_withdraw_formatted:,.2f} {borrow_symbol} ({max_withdraw_pct:.1f}%)\n"

    msg += (
        f"\n<b>Last Report:</b> {time_str}\n"
        f"<b>Tend Trigger:</b> {tend_status}\n"
        f"<b>Network:</b> {network_name}\n\n"
        f"<a href='{explorer_url}{address}'>🔗 View Strategy</a>"
    )

    await notify_group_chat(msg)


# =============================================================================
# Signer Balance Check
# =============================================================================


async def check_signer_balance(bot: TinyBot) -> None:
    if not bot.executor:
        return
    balance = bot.executor.balance
    min_balance = MIN_SIGNER_BALANCE if network() == "ethereum" else MIN_SIGNER_BALANCE // 10
    if balance < min_balance:
        await notify_group_chat(
            f"⚠️ <b>Low signer balance!</b>\n\n"
            f"<b>Balance:</b> {balance / 1e18:.4f} ETH\n"
            f"<b>Minimum:</b> {min_balance / 1e18:.4f} ETH\n"
            f"<b>Network:</b> {network().capitalize()}\n\n"
            f"<i>Checking again in {BALANCE_CHECK_INTERVAL // 3600} hours...</i>"
        )


# =============================================================================
# Uptime Ping
# =============================================================================


async def ping_uptime_monitor(bot: TinyBot) -> None:
    url = uptime_push_url()
    if not url:
        return
    try:
        req = Request(url, headers={"User-Agent": "ydegen-monitor-bot"})  # noqa: S310
        urlopen(req, timeout=10)  # noqa: S310
    except Exception as e:
        print(f"Uptime ping failed: {e}")


# =============================================================================
# Entry Point
# =============================================================================


async def run() -> None:
    from bot.config import NETWORK_RPC_ENVS

    rpc_url = os.environ.get("RPC_URL") or os.environ[NETWORK_RPC_ENVS.get(network(), "RPC_URL")]
    private_key = os.getenv("BOT_PRIVATE_KEY", "")

    bot = TinyBot(rpc_url=rpc_url, name=f"📡 {network()} yDegen", private_key=private_key)

    if network() == "ethereum":
        from bot.tg import start_command_listener

        start_command_listener()

    bot.every(interval=TEND_CHECK_INTERVAL, handler=check_tend_triggers)
    bot.every(interval=BALANCE_CHECK_INTERVAL, handler=check_signer_balance)
    bot.every(interval=UPTIME_PING_INTERVAL, handler=ping_uptime_monitor)

    bot.cron(expression=STATUS_REPORT_CRON, handler=report_status)

    await bot.run()
