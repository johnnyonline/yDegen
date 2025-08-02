import time
from typing import Annotated

from ape import chain
from ape.api import BlockAPI
from silverback import SilverbackBot, StateSnapshot
from taskiq import Context, TaskiqDepends

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
def exec_block(block: BlockAPI, context: Annotated[Context, TaskiqDepends()]) -> dict[str, float]:
    print(f"New block: {block.number}, timestamp: {block.timestamp}")
    print("starting to sleep for 20 seconds...")
    start = time.time()
    time.sleep(20)
    print("finished sleeping for 20 seconds...")
    # print the latest block number
    print(f"Latest block number: {chain.blocks[-1].number}")
    elapsed = time.time() - start
    return {"block_processing_time": elapsed}


# =============================================================================
# Metrics Handlers
# =============================================================================


@bot.on_metric("block_processing_time", gt=10)  # e.g. 10s threshold
def alert_slow_block(block_processing_time: float) -> None:
    print(f"🚨 Block processing took too long: {block_processing_time:.2f} seconds")
    # You could also send a Telegram alert or log it to a dashboard


# =============================================================================
# Cron Jobs
# =============================================================================

# @bot.cron("* * * * *")
# def some_cron_task(time):
#     ...
