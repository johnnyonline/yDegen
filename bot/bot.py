import itertools
import os
from datetime import datetime
from typing import Annotated

from ape import Contract, chain
from ape.api import BlockAPI
from ape_ethereum import multicall
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

from bot.config import (
    apr_oracle,
    chain_key,
    explorer_base_url,
    lender_borrower_strategies,
    liquity_coll_index,
    liquity_lender_borrower_strategies,
    strategies,
)
from bot.tg import ERROR_GROUP_CHAT_ID, notify_group_chat
from bot.utils import execute_tend, get_signer_balance, load_state, report_strategy, save_state

# =============================================================================
# Bot Configuration & Constants
# =============================================================================


bot = SilverbackBot()

STATUS_REPORT_CRON = os.getenv("STATUS_REPORT_CRON", "0 8 * * *")  # Daily at 8 AM UTC
# STATUS_REPORT_CRON = os.getenv("STATUS_REPORT_CRON", "* * * * *")  # Every minute (for testing)
ALERT_COOLDOWN_SECONDS = int(os.getenv("TEND_TRIGGER_ALERT_COOLDOWN_SECONDS", "7200"))  # 2 hours default
MIN_SIGNER_BALANCE = int(os.getenv("MIN_SIGNER_BALANCE", str(5 * 10**16)))  # 0.05 ETH default
BALANCE_CHECK_CRON = os.getenv("BALANCE_CHECK_CRON", "0 */5 * * *")  # Every 5 hours


# =============================================================================
# Startup / Shutdown
# =============================================================================


@bot.on_startup()  # type: ignore[untyped-decorator]
async def bot_startup(startup_state: StateSnapshot) -> None:
    await notify_group_chat(
        f"🟢 <b>{chain_key()} yDegen bot started successfully</b>",
        chat_id=ERROR_GROUP_CHAT_ID,
    )


@bot.on_shutdown()  # type: ignore[untyped-decorator]
async def bot_shutdown() -> None:
    await notify_group_chat(
        f"🔴 <b>{chain_key()} yDegen bot shutdown successfully</b>",
        chat_id=ERROR_GROUP_CHAT_ID,
    )


# =============================================================================
# Chain Events
# =============================================================================


@bot.on_(chain.blocks)  # type: ignore[untyped-decorator]
async def check_tend_triggers(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]) -> None:
    # Only run every 100th block if not mainnet
    chain = chain_key()
    if chain != "ethereum" and (block.number % 100 != 0):
        return

    # Get current strategies. Skip if none found
    current_strategies = list(strategies())
    if not current_strategies:
        return

    # Prepare multicall for all strategy data
    call = multicall.Call()
    for strategy in current_strategies:
        strategy = Contract(strategy.address, abi="bot/abis/IBaseStrategy.json")  # Loading ABI manually
        call.add(strategy.tendTrigger)

    # Execute the multicall
    results = call()

    # Cache timestamp and block number
    now_ts = block.timestamp
    block_number = block.number

    # Process results and notify if needed
    for strategy, (needs_tend, _data) in zip(current_strategies, results):
        if not needs_tend:
            continue

        # Check cooldown
        state = load_state()
        last_ts = state.get("tend_alerts_ts", {}).get(strategy.address, 0)
        if now_ts - last_ts < ALERT_COOLDOWN_SECONDS:
            continue

        strategy = Contract(strategy.address, abi="bot/abis/ITokenizedStrategy.json")  # Loading ABI manually

        # Update the timestamp in state
        state.setdefault("tend_alerts_ts", {})[strategy.address] = now_ts
        save_state(state)

        await notify_group_chat(
            f"🚨 <b>Strategy needs tending!</b>\n\n"
            f"<b>Name:</b> {strategy.name()}\n"
            f"<b>Network:</b> {chain.capitalize()}\n"
            f"<b>Block Number:</b> {block_number}\n\n"
            f"<i>Attempting to tend...</i>\n"
            f"<i>Sleeping for {int(ALERT_COOLDOWN_SECONDS / 60)} minutes...</i>\n\n"
            f"<a href='{explorer_base_url()}{strategy.address}'>🔗 View Strategy</a>"
        )

        tx_hash = execute_tend(strategy.address)
        if tx_hash:
            await notify_group_chat(
                f"✅ <b>Tend tx submitted</b>\n\n"
                f"<a href='{explorer_base_url().replace('/address/', '/tx/')}{tx_hash}'>🔗 View Transaction</a>"
            )


# @bot.on_(chain.blocks)
async def check_still_profitable(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]) -> None:
    # Only run every 5th block if not Ethereum mainnet
    chain = chain_key()
    if chain != "ethereum" and (block.number % 5 != 0):
        return

    # Cache the APR oracle instance
    oracle = apr_oracle()

    # Get current lender borrower strategies. Skip if none found
    current_strategies = list(lender_borrower_strategies())
    if not current_strategies:
        return

    # Prepare multicall for all strategy data
    call = multicall.Call()
    for strategy in current_strategies:
        strategy = Contract(strategy.address, abi="bot/abis/ITokenizedStrategy.json")  # Loading ABI manually
        call.add(strategy.totalAssets)
        call.add(oracle.getStrategyApr, strategy.address, 0)

    # Execute the multicall
    results = call()

    # Cache timestamp
    now_ts = block.timestamp

    # Check if any strategy is not profitable and notify if needed
    for strategy, (total_assets, apr) in zip(current_strategies, itertools.batched(results, n=2)):
        if total_assets == 0:
            continue  # No assets

        if apr > 0:
            continue  # All good

        # Check cooldown
        state = load_state()
        last_ts = state.get("apr_zero_alert_ts", {}).get(strategy.address, 0)
        if now_ts - last_ts < ALERT_COOLDOWN_SECONDS:
            continue

        strategy = Contract(strategy.address, abi="bot/abis/ITokenizedStrategy.json")  # Loading ABI manually

        await notify_group_chat(
            f"🚨 <b>Expected APR is zero!</b>\n\n"
            f"<b>Name:</b> {strategy.name()}\n"
            f"<b>Network:</b> {chain.capitalize()}\n"
            f"<b>Block Number:</b> {block.number}\n\n"
            f"<i>Sleeping for {int(ALERT_COOLDOWN_SECONDS / 60)} minutes...</i>\n\n"
            f"<a href='{explorer_base_url()}{strategy.address}'>🔗 View Strategy</a>"
        )

        # Update the timestamp in state
        state.setdefault("apr_zero_alert_ts", {})[strategy.address] = now_ts
        save_state(state)


# =============================================================================
# Cron Jobs
# =============================================================================


@bot.cron(STATUS_REPORT_CRON)  # type: ignore[untyped-decorator]
async def report_status(time: datetime) -> None:
    # Combine regular and liquity lender borrower strategies
    regular_strategies = list(lender_borrower_strategies())
    liquity_strategies = list(liquity_lender_borrower_strategies())
    liquity_addresses = {s.address for s in liquity_strategies}
    all_strategies = regular_strategies + liquity_strategies

    if not all_strategies:
        return

    # Cache frequently used values
    now_ts = int(time.timestamp())
    oracle = apr_oracle()
    network = chain_key().capitalize()
    explorer_url = explorer_base_url()

    for strategy in all_strategies:
        is_liquity = strategy.address in liquity_addresses
        coll_index = liquity_coll_index(strategy.address) if is_liquity else 0
        await report_strategy(strategy, is_liquity, coll_index, now_ts, oracle, network, explorer_url)


@bot.cron(BALANCE_CHECK_CRON)  # type: ignore[untyped-decorator]
async def check_signer_balance(time: datetime) -> None:
    balance = get_signer_balance()
    min_balance = MIN_SIGNER_BALANCE if chain_key() == "ethereum" else MIN_SIGNER_BALANCE // 10
    if balance < min_balance:
        await notify_group_chat(
            f"⚠️ <b>Low signer balance!</b>\n\n"
            f"<b>Balance:</b> {balance / 1e18:.4f} ETH\n"
            f"<b>Minimum:</b> {min_balance / 1e18:.4f} ETH\n"
            f"<b>Network:</b> {chain_key().capitalize()}\n\n"
            f"<i>Checking again in 5 hours...</i>"
        )
