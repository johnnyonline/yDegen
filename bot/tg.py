import asyncio
import os
import random
import threading

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from tinybot import multicall
from tinybot.tg import BOT_ACCESS_TOKEN, DEV_GROUP_CHAT_ID, GROUP_CHAT_ID
from web3 import Web3

from bot.config import (
    BASE_STRATEGY_ABI,
    EMOJIS,
    LENDER_BORROWER_ABI,
    LOOPER_ABI,
    NETWORK_RPC_ENVS,
    NETWORKS,
    TOKENIZED_STRATEGY_ABI,
    w3_contract,
)


def _get_w3(network_key: str) -> Web3 | None:
    rpc_url = os.getenv(NETWORK_RPC_ENVS.get(network_key, ""), "")
    if not rpc_url:
        return None
    return Web3(Web3.HTTPProvider(rpc_url))


def _build_network_status(network_key: str) -> str | None:
    w3 = _get_w3(network_key)
    if not w3:
        return None

    network_cfg = NETWORKS[network_key]
    lb_addrs = list(network_cfg["lender_borrowers"])
    liquity_addrs = list(network_cfg["liquity_lender_borrowers"].keys())
    ybold_addrs = list(network_cfg["ybold"])
    looper_addrs = list(network_cfg["morpho_loopers"]) + list(network_cfg["aave_loopers"])
    all_addrs = lb_addrs + liquity_addrs + ybold_addrs + looper_addrs

    if not all_addrs:
        return None

    ltv_addrs = lb_addrs + liquity_addrs + looper_addrs
    ltv_addr_set = set(ltv_addrs)

    tend_results = multicall(w3, [w3_contract(w3, a, BASE_STRATEGY_ABI).functions.tendTrigger() for a in all_addrs])
    name_results = multicall(w3, [w3_contract(w3, a, TOKENIZED_STRATEGY_ABI).functions.name() for a in all_addrs])

    ltv_map: dict[str, float] = {}
    if ltv_addrs:
        # Loopers use LOOPER_ABI; lender-borrowers use LENDER_BORROWER_ABI. Both have getCurrentLTV().
        ltv_calls = []
        looper_set = set(looper_addrs)
        for a in ltv_addrs:
            abi = LOOPER_ABI if a in looper_set else LENDER_BORROWER_ABI
            ltv_calls.append(w3_contract(w3, a, abi).functions.getCurrentLTV())
        ltv_results = multicall(w3, ltv_calls)
        for addr, raw_ltv in zip(ltv_addrs, ltv_results):
            ltv_map[addr] = raw_ltv / 1e16

    lines = [f"{random.choice(EMOJIS)} <b>{network_key.capitalize()}</b>"]
    for addr, name, (needs_tend, _) in zip(all_addrs, name_results, tend_results):
        line = f"<b>Name:</b> {name}\n"
        line += f"<b>Tend Trigger:</b> {needs_tend}"
        if addr in ltv_addr_set:
            line += f"\n<b>LTV:</b> {ltv_map.get(addr, 0.0):.1f}%"
        lines.append(line)

    return "\n\n".join(lines)


def build_status_messages() -> list[str]:
    messages = []
    for network_key in NETWORKS:
        try:
            msg = _build_network_status(network_key)
            if msg:
                messages.append(msg)
        except Exception as e:
            messages.append(f"{random.choice(EMOJIS)} <b>{network_key.capitalize()}</b>\n\nFailed: {e}")
    return messages


async def _status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.id not in (GROUP_CHAT_ID, DEV_GROUP_CHAT_ID):
        return

    try:
        messages = build_status_messages()
    except Exception as e:
        messages = [f"Failed to fetch status: {e}"]

    if not messages:
        messages = ["No strategies configured."]

    for msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)  # type: ignore[union-attr]


def start_command_listener() -> None:
    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = Application.builder().token(BOT_ACCESS_TOKEN).build()
        app.add_handler(CommandHandler("status", _status_command))
        loop.run_until_complete(app.initialize())
        loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))  # type: ignore[union-attr]
        loop.run_until_complete(app.start())
        loop.run_forever()

    threading.Thread(target=_run, daemon=True).start()
