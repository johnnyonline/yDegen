import itertools
import os
import random
from datetime import datetime
from typing import Annotated

from ape import chain
from ape.api import BlockAPI
from ape_ethereum import multicall
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

from bot.config import EMOJIS, apr_oracle, chain_key, explorer_base_url, strategies
from bot.tg import ERROR_GROUP_CHAT_ID, notify_group_chat

# =============================================================================
# Bot Configuration & Constants
# =============================================================================


bot = SilverbackBot()

STATUS_REPORT_CRON = os.getenv("STATUS_REPORT_CRON", "0 8 * * *")  # Daily at 8 AM UTC
ALERT_COOLDOWN_SECONDS = int(os.getenv("TEND_TRIGGER_ALERT_COOLDOWN_SECONDS", "3600"))  # 1 hour default


# =============================================================================
# Startup / Shutdown
# =============================================================================


@bot.on_startup()
async def bot_startup(startup_state: StateSnapshot) -> None:
    await notify_group_chat(
        f"🟢 <b>{chain_key()} yDegen bot started successfully</b>",
        chat_id=ERROR_GROUP_CHAT_ID,
    )

    # Set `bot.state` values
    bot.state.tend_alerts_ts = {}
    bot.state.apr_zero_alert_ts = {}


@bot.on_shutdown()
async def bot_shutdown() -> None:
    await notify_group_chat(
        f"🔴 <b>{chain_key()} yDegen bot shutdown successfully</b>",
        chat_id=ERROR_GROUP_CHAT_ID,
    )


# =============================================================================
# Chain Events
# =============================================================================


@bot.on_(chain.blocks)
async def check_tend_triggers(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]) -> None:
    # Only run every 5th block if not mainnet
    chain = chain_key()
    if chain != "ethereum" and (block.number % 5 != 0):
        return

    # Prepare multicall for all strategy data
    current_strategies = list(strategies())
    call = multicall.Call()
    for strategy in current_strategies:
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
        last_ts = bot.state.tend_alerts_ts.get(strategy.address, 0)
        if now_ts - last_ts < ALERT_COOLDOWN_SECONDS:
            continue

        await notify_group_chat(
            f"🚨 <b>Strategy needs tending!</b>\n\n"
            f"<b>Name:</b> {strategy.name()}\n"
            f"<b>Network:</b> {chain.capitalize()}\n"
            f"<b>Block Number:</b> {block_number}\n\n"
            f"<i>Sleeping for {int(ALERT_COOLDOWN_SECONDS / 60)} minutes...</i>\n\n"
            f"<a href='{explorer_base_url()}{strategy.address}'>🔗 View Strategy</a>"
        )

        # Update the timestamp in state
        bot.state.tend_alerts_ts[strategy.address] = now_ts


@bot.on_(chain.blocks)
async def check_still_profitable(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]) -> None:
    # Only run every 5th block if not Ethereum mainnet
    chain = chain_key()
    if chain != "ethereum" and (block.number % 5 != 0):
        return

    # Cache the APR oracle instance
    oracle = apr_oracle()

    # Prepare multicall for all strategy data
    current_strategies = list(strategies())
    call = multicall.Call()
    for strategy in current_strategies:
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
        last_ts = bot.state.apr_zero_alert_ts.get(strategy.address, 0)
        if now_ts - last_ts < ALERT_COOLDOWN_SECONDS:
            continue

        await notify_group_chat(
            f"🚨 <b>Expected APR is zero!</b>\n\n"
            f"<b>Name:</b> {strategy.name()}\n"
            f"<b>Network:</b> {chain.capitalize()}\n"
            f"<b>Block Number:</b> {block.number}\n\n"
            f"<i>Sleeping for {int(ALERT_COOLDOWN_SECONDS / 60)} minutes...</i>\n\n"
            f"<a href='{explorer_base_url()}{strategy.address}'>🔗 View Strategy</a>"
        )

        # Update the timestamp in state
        bot.state.apr_zero_alert_ts[strategy.address] = now_ts


# =============================================================================
# Cron Jobs
# =============================================================================


@bot.cron(STATUS_REPORT_CRON)
async def report_status(time: datetime) -> None:
    # Prepare multicall for all strategy data
    current_strategies = list(strategies())
    call = multicall.Call()
    for strategy in current_strategies:
        call.add(strategy.name)
        call.add(strategy.getCurrentLTV)
        call.add(strategy.getLiquidateCollateralFactor)
        call.add(strategy.targetLTVMultiplier)
        call.add(strategy.warningLTVMultiplier)

    # Execute the multicall
    results = call()

    # Process results in batches of 5 per strategy
    for strategy, (
        name,
        raw_current_ltv,
        collateral_factor,
        target_ltv_mult,
        warning_ltv_mult,
    ) in zip(current_strategies, itertools.batched(results, n=5)):
        liquidation_threshold = collateral_factor / 1e16
        msg = (
            f"{random.choice(EMOJIS)} <b>{name}</b>\n\n"
            f"<b>LTV:</b> {raw_current_ltv / 1e16:.1f}%\n"
            f"<b>Target:</b> {liquidation_threshold * target_ltv_mult / 1e4:.1f}%\n"
            f"<b>Warning:</b> {liquidation_threshold * warning_ltv_mult / 1e4:.1f}%\n"
            f"<b>Liquidation:</b> {liquidation_threshold:.1f}%\n"
            f"<b>Expected APR:</b> {int(apr_oracle().getStrategyApr(strategy.address, 0)) / 1e16:.2f}%\n\n"
            f"<a href='{explorer_base_url()}{strategy.address}'>🔗 View Strategy</a>"
        )

        await notify_group_chat(msg)
