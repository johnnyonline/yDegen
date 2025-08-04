import random
from typing import Annotated

from ape import chain
from ape.api import BlockAPI
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

from src.addresses import EMOJIS, eth_oracle, strategies
from src.tg import ERROR_GROUP_CHAT_ID, notify_group_chat

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

    # Notify about each strategy's status
    for strategy in strategies("eth"):
        name = strategy.name()
        ltv = strategy.getCurrentLTV() / 1e16
        liquidation_threshold = strategy.getLiquidateCollateralFactor() / 1e16
        target_ltv = liquidation_threshold * strategy.targetLTVMultiplier() / 1e4
        warning_ltv = liquidation_threshold * strategy.warningLTVMultiplier() / 1e4
        borrow_apr = strategy.getNetBorrowApr(0) / 1e16
        reward_apr = strategy.getNetRewardApr(0) / 1e16
        msg = (
            f"{random.choice(EMOJIS)} <b>{name}</b>\n\n"
            f"<b>LTV:</b> {ltv:.1f}%\n"
            f"<b>Target:</b> {target_ltv:.1f}%\n"
            f"<b>Warning:</b> {warning_ltv:.1f}%\n"
            f"<b>Liquidation:</b> {liquidation_threshold:.1f}%\n"
            f"<b>Borrow APR:</b> {borrow_apr:.2f}%\n"
            f"<b>Reward APR:</b> {reward_apr:.2f}%\n\n"
            f"<a href='https://etherscan.io/address/{strategy.address}'>🔗 View Strategy</a>"
        )

        await notify_group_chat(msg)
