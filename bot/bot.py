import itertools
import random
from typing import Annotated

from ape import chain
from ape.api import BlockAPI
from ape_ethereum import multicall
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

from bot.addresses import EMOJIS, eth_oracle, strategies
from bot.tg import ERROR_GROUP_CHAT_ID, notify_group_chat

bot = SilverbackBot()

# =============================================================================
# Startup / Shutdown
# =============================================================================


@bot.on_startup()
async def bot_startup(startup_state: StateSnapshot) -> None:
    await notify_group_chat(
        "🟢 <b>yDegen bot started successfully!</b>", chat_id=ERROR_GROUP_CHAT_ID
    )


@bot.on_shutdown()
async def bot_shutdown() -> None:
    await notify_group_chat(
        "🔴 <b>yDegen bot shutdown successfully!</b>", chat_id=ERROR_GROUP_CHAT_ID
    )


# =============================================================================
# Chain Events
# =============================================================================


@bot.on_(chain.blocks)
async def check_tend_triggers(
    block: BlockAPI, context: Annotated[Context, TaskiqDepends()]
) -> None:
    # Check if any strategy needs tending and notify
    for strategy in strategies():
        needs_tend, _ = strategy.tendTrigger()
        if needs_tend:
            await notify_group_chat(
                f"🚨 <b>Strategy needs tending!</b>\n\n"
                f"<b>Name:</b> {strategy.name()}\n"
                f"<b>Block Number:</b> {block.number}\n\n"
                f"<a href='https://etherscan.io/address/{strategy.address}'>🔗 View Strategy</a>"
            )


@bot.on_(eth_oracle().AnswerUpdated)
async def on_eth_price_update(event) -> None:  # type: ignore
    # Notify about ETH price update
    msg = f"{random.choice(EMOJIS)} <b>ETH price updated</b>\n\n<b>Price:</b> {int(event.current / 1e8)} USD"
    await notify_group_chat(msg)

    # Prepare multicall for all strategy data
    current_strategies = list(strategies("eth"))
    call = multicall.Call()
    for strategy in current_strategies:
        call.add(strategy.name)
        call.add(strategy.getCurrentLTV)
        call.add(strategy.getLiquidateCollateralFactor)
        call.add(strategy.targetLTVMultiplier)
        call.add(strategy.warningLTVMultiplier)
        call.add(strategy.getNetBorrowApr, 0)
        call.add(strategy.getNetRewardApr, 0)

    # Execute the multicall
    results = call()

    # Process results in batches of 7 per strategy
    for strategy, (
        name,
        raw_current_ltv,
        collateral_factor,
        target_ltv_mult,
        warning_ltv_mult,
        borrow_apr,
        reward_apr,
    ) in zip(current_strategies, itertools.batched(results, n=7)):
        liquidation_threshold = collateral_factor / 1e16
        msg = (
            f"{random.choice(EMOJIS)} <b>{name}</b>\n\n"
            f"<b>LTV:</b> {raw_current_ltv / 1e16:.1f}%\n"
            f"<b>Target:</b> {liquidation_threshold * target_ltv_mult / 1e4:.1f}%\n"
            f"<b>Warning:</b> {liquidation_threshold * warning_ltv_mult / 1e4:.1f}%\n"
            f"<b>Liquidation:</b> {liquidation_threshold:.1f}%\n"
            f"<b>Borrow APR:</b> {borrow_apr / 1e16:.2f}%\n"
            f"<b>Reward APR:</b> {reward_apr / 1e16:.2f}%\n\n"
            f"<a href='https://etherscan.io/address/{strategy.address}'>🔗 View Strategy</a>"
        )

        await notify_group_chat(msg)
