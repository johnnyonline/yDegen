import asyncio
import json
import os
import random
import threading
from urllib.request import Request, urlopen

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from tinybot import multicall
from tinybot.tg import BOT_ACCESS_TOKEN, DEV_GROUP_CHAT_ID, GROUP_CHAT_ID
from web3 import Web3

CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "base": 8453,
    "arbitrum": 42161,
    "katana": 747474,
    "polygon": 137,
}


def _fetch_kong_snapshot(chain_id: int, vault_addr: str) -> dict | None:
    """Fetch Yearn Kong snapshot for a vault. Returns None on any failure."""
    url = f"https://kong.yearn.fi/api/rest/snapshot/{chain_id}/{vault_addr}"
    try:
        req = Request(url, headers={"User-Agent": "ydegen-monitor-bot"})  # noqa: S310
        with urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.load(resp)  # type: ignore[no-any-return]
    except Exception:
        return None

from bot.config import (
    BASE_STRATEGY_ABI,
    EMOJIS,
    ERC20_ABI,
    LENDER_BORROWER_ABI,
    LOOPER_ABI,
    MULTI_STRATEGY_VAULT_TYPE,
    NETWORK_RPC_ENVS,
    NETWORKS,
    REGISTRY_ABI,
    REGISTRY_ADDRESSES,
    TOKENIZED_STRATEGY_ABI,
    VAULT_ABI,
    w3_contract,
)


def _get_w3(network_key: str) -> Web3 | None:
    rpc_url = os.getenv(NETWORK_RPC_ENVS.get(network_key, ""), "")
    if not rpc_url:
        return []
    return Web3(Web3.HTTPProvider(rpc_url))


def _build_network_status(network_key: str) -> str | None:
    w3 = _get_w3(network_key)
    if not w3:
        return []

    network_cfg = NETWORKS[network_key]
    lb_addrs = list(network_cfg["lender_borrowers"])
    liquity_addrs = list(network_cfg["liquity_lender_borrowers"].keys())
    ybold_addrs = list(network_cfg["ybold"])
    looper_addrs = list(network_cfg["morpho_loopers"]) + list(network_cfg["aave_loopers"])
    all_addrs = lb_addrs + liquity_addrs + ybold_addrs + looper_addrs

    if not all_addrs:
        return []

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


def _chunk_messages(header: str, blocks: list[str], max_len: int = 3500) -> list[str]:
    """Pack vault blocks into Telegram-sized messages, repeating the header per chunk."""
    chunks = []
    current = header
    for block in blocks:
        if len(current) + len(block) + 2 > max_len:
            chunks.append(current)
            current = header
        current += "\n\n" + block
    if current != header:
        chunks.append(current)
    return chunks


# Min-amount thresholds by asset category. Symbols are matched lowercased.
_STABLE_SYMBOLS = {
    "usdc", "usdt", "dai", "usds", "usde", "susde", "frax", "lusd", "gho",
    "rlusd", "pyusd", "bold", "crvusd", "usdaf", "usnd", "ysusd", "usdc.e",
    "tusd", "yvusd", "yvbold", "vbUSDS", "vbUSDT",
}
_ETH_SYMBOLS = {
    "weth", "eth", "steth", "wsteth", "reth", "cbeth", "frxeth", "sfrxeth",
    "weeth", "ezeth", "oeth",
}
_BTC_SYMBOLS = {"wbtc", "cbbtc", "tbtc", "lbtc", "btc", "wbtc18", "vbwbtc"}


def _min_amount(symbol: str) -> float:
    s = symbol.lower()
    if s in _STABLE_SYMBOLS:
        return 5_000.0
    if s in _ETH_SYMBOLS:
        return 5.0
    if s in _BTC_SYMBOLS:
        return 0.5
    return 0.0  # show unknown assets always


def _build_network_exposure(network_key: str) -> list[str]:
    w3 = _get_w3(network_key)
    if not w3:
        return []

    explorer = NETWORKS[network_key]["explorer"]

    # 1. Collect endorsed vaults from BOTH registries, tracking which registry knows each vault
    vault_addrs: list[str] = []
    registry_for_vault: dict[str, str] = {}
    for registry_addr in REGISTRY_ADDRESSES:
        registry = w3_contract(w3, registry_addr, REGISTRY_ABI)
        try:
            nested = registry.functions.getAllEndorsedVaults().call()
            for sub in nested:
                for a in sub:
                    key = a.lower()
                    if key not in registry_for_vault:
                        registry_for_vault[key] = registry_addr
                        vault_addrs.append(a)
        except Exception:
            continue

    if not vault_addrs:
        return []

    # 2. Multicall vaultInfo against the registry that actually knows each vault
    info_calls = []
    for addr in vault_addrs:
        reg_addr = registry_for_vault[addr.lower()]
        registry = w3_contract(w3, reg_addr, REGISTRY_ABI)
        info_calls.append(registry.functions.vaultInfo(Web3.to_checksum_address(addr)))
    info_results = multicall(w3, info_calls)

    multi_strategy_vaults: list[str] = []
    for addr, info in zip(vault_addrs, info_results):
        # info: (asset, releaseVersion, vaultType, deploymentTimestamp, index, tag)
        try:
            if info[2] == MULTI_STRATEGY_VAULT_TYPE:
                multi_strategy_vaults.append(addr)
        except Exception:
            continue

    if not multi_strategy_vaults:
        return []

    # 3. Multicall vault details: name, asset, totalAssets, decimals, get_default_queue
    vault_calls = []
    for addr in multi_strategy_vaults:
        v = w3_contract(w3, addr, VAULT_ABI)
        vault_calls.extend([
            v.functions.name(),
            v.functions.asset(),
            v.functions.totalAssets(),
            v.functions.decimals(),
            v.functions.get_default_queue(),
        ])
    vault_results = multicall(w3, vault_calls)

    # 4. Collect unique asset + strategy addresses
    strategies_per_vault: list[list[str]] = []
    asset_addrs: list[str] = []
    strategy_addrs_set: set[str] = set()
    for i in range(len(multi_strategy_vaults)):
        base = i * 5
        asset_addrs.append(vault_results[base + 1])
        strategies = list(vault_results[base + 4])
        strategies_per_vault.append(strategies)
        for s in strategies:
            strategy_addrs_set.add(s.lower())

    # 5. Multicall asset symbols + idle (asset.balanceOf(vault)) per vault
    asset_symbols: list[str] = []
    idle_map: dict[str, int] = {}
    if asset_addrs:
        sym_calls = [w3_contract(w3, a, ERC20_ABI).functions.symbol() for a in asset_addrs]
        idle_calls = [
            w3_contract(w3, a, ERC20_ABI).functions.balanceOf(Web3.to_checksum_address(v))
            for a, v in zip(asset_addrs, multi_strategy_vaults)
        ]
        sym_results = multicall(w3, sym_calls + idle_calls)
        asset_symbols = sym_results[: len(asset_addrs)]
        for v, idle in zip(multi_strategy_vaults, sym_results[len(asset_addrs):]):
            idle_map[v.lower()] = idle

    # 6. Pull strategy names + debts from Kong (one call per vault).
    #    Composition includes both queued strategies (debt may be 0) and any orphan with non-zero debt.
    strategy_name_map: dict[str, str] = {}
    balance_map: dict[tuple[str, str], int] = {}
    extras_per_vault: list[list[tuple[str, int]]] = [[] for _ in multi_strategy_vaults]
    chain_id = CHAIN_IDS.get(network_key)
    if chain_id is not None:
        for i, vault_addr in enumerate(multi_strategy_vaults):
            queue_set = {s.lower() for s in strategies_per_vault[i]}
            snapshot = _fetch_kong_snapshot(chain_id, vault_addr)
            if not snapshot:
                continue
            for entry in snapshot.get("composition", []) or []:
                addr = entry.get("address", "")
                if not addr:
                    continue
                debt = int(str(entry.get("currentDebt", "0")))
                ename = entry.get("name", addr)
                strategy_name_map[addr.lower()] = ename
                if addr.lower() in queue_set:
                    balance_map[(vault_addr.lower(), addr.lower())] = debt
                elif debt != 0:
                    extras_per_vault[i].append((addr, debt))

    # 7. Build vault blocks (skip below threshold + name filters)
    blocks: list[str] = []
    for i, vault_addr in enumerate(multi_strategy_vaults):
        base = i * 5
        name = vault_results[base]
        total_assets = vault_results[base + 2]
        decimals = vault_results[base + 3]
        strategies = strategies_per_vault[i]
        symbol = asset_symbols[i] if i < len(asset_symbols) else "?"
        scale = 10**decimals

        # Skip excluded families
        if any(x in name for x in ("Liquid Locker Compounder", "Balancer", "yYB", "mkUSD", "yPRISMA-1")):
            continue

        # Only include known vault families
        if not any(x in name for x in ("yVault", "BOLD", "USDaf")):
            continue

        amount = total_assets / scale
        if amount < _min_amount(symbol):
            continue

        vault_link = f"<a href='{explorer}{vault_addr}'>{name}</a>"
        idle_amount = idle_map.get(vault_addr.lower(), 0) / scale
        block = f"📦 <b>{vault_link}</b> — {amount:,.2f} {symbol} ({idle_amount:,.2f} idle)"
        for s in strategies:
            sname = strategy_name_map.get(s.lower(), s)
            s_balance = balance_map.get((vault_addr.lower(), s.lower()), 0)
            s_amount = s_balance / scale
            strat_link = f"<a href='{explorer}{s}'>{sname}</a>"
            block += f"\n  ↳ {strat_link} — {s_amount:,.2f} {symbol}"
        for extra_addr, extra_debt in extras_per_vault[i]:
            ename = strategy_name_map.get(extra_addr.lower(), extra_addr)
            e_amount = extra_debt / scale
            elink = f"<a href='{explorer}{extra_addr}'>{ename}</a>"
            block += f"\n  ↳ {elink} — {e_amount:,.2f} {symbol} <i>(not in default queue)</i>"
        blocks.append(block)

    if not blocks:
        return []

    header = f"{random.choice(EMOJIS)} <b>{network_key.capitalize()}</b>"
    return _chunk_messages(header, blocks)


def build_exposure_messages() -> list[str]:
    messages = []
    for network_key in NETWORKS:
        try:
            messages.extend(_build_network_exposure(network_key))
        except Exception as e:
            messages.append(f"{random.choice(EMOJIS)} <b>{network_key.capitalize()}</b>\n\nFailed: {e}")
    return messages


async def _exposure_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.id not in (GROUP_CHAT_ID, DEV_GROUP_CHAT_ID):
        return

    try:
        messages = build_exposure_messages()
    except Exception as e:
        messages = [f"Failed to fetch exposure: {e}"]

    if not messages:
        messages = ["No multi-strategy vaults found."]

    for msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)  # type: ignore[union-attr]
        await asyncio.sleep(0.5)


def start_command_listener() -> None:
    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = Application.builder().token(BOT_ACCESS_TOKEN).build()
        app.add_handler(CommandHandler("status", _status_command))
        app.add_handler(CommandHandler("exposure", _exposure_command))
        loop.run_until_complete(app.initialize())
        loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))  # type: ignore[union-attr]
        loop.run_until_complete(app.start())
        loop.run_forever()

    threading.Thread(target=_run, daemon=True).start()
