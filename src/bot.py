import time
from typing import Annotated

from ape import chain
from ape.api import BlockAPI
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

from src.tg import notify_group_chat

bot = SilverbackBot()

# =============================================================================
# Startup / Shutdown
# =============================================================================


@bot.on_startup()
def bot_startup(startup_state: StateSnapshot) -> None:
    print("Worker started successfully!")


@bot.on_shutdown()
def bot_shutdown() -> None:
    print("Worker shutdown successfully!")


# =============================================================================
# Chain Events
# =============================================================================


@bot.on_(chain.blocks)
async def exec_block(
    block: BlockAPI, context: Annotated[Context, TaskiqDepends()]
) -> dict[str, float]:
    print(f"New block: {block.number}, timestamp: {block.timestamp}")
    start = time.time()
    msg = f"📦 New block: <b>{block.number}</b>"
    await notify_group_chat(msg)
    elapsed = time.time() - start
    return {"block_processing_time": elapsed}


# =============================================================================
# Metrics Handlers
# =============================================================================


@bot.on_metric("block_processing_time", gt=10)
def alert_slow_block(block_processing_time: float) -> None:
    print(f"🚨 Block processing took too long: {block_processing_time:.2f} seconds")


# =============================================================================
# Cron Jobs
# =============================================================================

# @bot.cron("* * * * *")
# def some_cron_task(time):
#     ...
