import os

from tinybot import TinyBot, telegram_enabled

from bot.config import (
    VAULT_ABI,
    allocator_vault_addrs,
    keeper_interval,
    network,
    private_rpc_url,
)
from bot.keeper import check_tend_triggers, report_keeper_digest, run_keeper
from bot.monitor import (
    BALANCE_CHECK_INTERVAL,
    check_signer_balance,
    on_vault_event,
    ping_uptime_monitor,
    report_status,
)

# =============================================================================
# Constants
# =============================================================================

TEND_CHECK_INTERVAL = int(os.getenv("TEND_CHECK_INTERVAL", "60"))  # 60 seconds default
STATUS_REPORT_CRON = os.getenv("STATUS_REPORT_CRON", "0 8 * * *")  # Daily at 8 AM UTC
UPTIME_PING_INTERVAL = int(os.getenv("UPTIME_PING_INTERVAL", "540"))  # 9 minutes default
VAULT_EVENT_POLL_INTERVAL = int(os.getenv("VAULT_EVENT_POLL_INTERVAL", "180"))  # 3 minutes default

# =============================================================================
# Entry Point
# =============================================================================


async def run() -> None:
    from bot.config import NETWORK_RPC_ENVS

    rpc_url = os.environ.get("RPC_URL") or os.environ[NETWORK_RPC_ENVS.get(network(), "RPC_URL")]
    private_key = os.getenv("TEND_PRIVATE_KEY", "")
    harvest_key = os.getenv("HARVEST_PRIVATE_KEY", "")

    bot = TinyBot(
        rpc_url=rpc_url,
        private_rpc_url=private_rpc_url(),
        name=f"👩‍🍼 {network()} vaults-mommy",
        private_key=private_key,
    )
    if harvest_key:
        bot.add_executor("harvest", harvest_key)

    bot.every(interval=TEND_CHECK_INTERVAL, handler=check_tend_triggers)
    bot.every(interval=keeper_interval(), handler=run_keeper)
    bot.every(interval=UPTIME_PING_INTERVAL, handler=ping_uptime_monitor)

    # Everything below only posts to Telegram; a tend-only instance runs without it
    if not telegram_enabled():
        await bot.run()
        return

    if network() == "ethereum":
        from bot.tg import start_command_listener

        start_command_listener()

    bot.every(interval=BALANCE_CHECK_INTERVAL, handler=check_signer_balance)
    bot.cron(expression=STATUS_REPORT_CRON, handler=report_status)
    bot.cron(expression=STATUS_REPORT_CRON, handler=report_keeper_digest)

    vault_addrs = allocator_vault_addrs()
    if vault_addrs:
        for event_name in ("Deposit", "Withdraw", "StrategyReported"):
            bot.listen(
                event=event_name,
                addresses=vault_addrs,
                abi=VAULT_ABI,
                handler=on_vault_event,
                name=f"vault_{event_name.lower()}",
                poll_interval=VAULT_EVENT_POLL_INTERVAL,
            )

    await bot.run()
