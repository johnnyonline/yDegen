import html
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from eth_abi.abi import decode
from tinybot import DEV_GROUP_CHAT_ID, TinyBot, multicall, notify_group_chat
from web3 import Web3
from web3.contract import Contract
from web3.contract.contract import ContractFunction
from web3.exceptions import ContractLogicError, TimeExhausted, TransactionNotFound

from bot.config import (
    BASE_STRATEGY_ABI,
    COMMON_REPORT_TRIGGER,
    COMMON_REPORT_TRIGGER_ABI,
    DEBT_ALLOCATOR_ABI,
    PERMISSIONLESS_RELAYER,
    PERMISSIONLESS_RELAYER_ABI,
    REGISTRY_ABI,
    REGISTRY_ADDRESSES,
    RELAYER_ABI,
    ROLE_MANAGER_ABI,
    TOKENIZED_STRATEGY_ABI,
    VAULT_ABI,
    all_strategy_addrs,
    explorer_base_url,
    keeper_extra_strategies,
    keeper_include_addrs,
    keeper_skip_addrs,
    network,
    private_rpc_url,
    relayer_addrs,
    w3_contract,
)
from bot.utils import load_state, save_state

# =============================================================================
# Constants
# =============================================================================

TEND_RETRY_SECONDS = int(os.getenv("TEND_RETRY_SECONDS", "600"))  # 10 minutes default
WARN_COOLDOWN_SECONDS = 24 * 60 * 60
DAY_SECONDS = 24 * 60 * 60

MAINNET_TEND_TIP_GWEI = 3.0
MIN_TEND_TIP_GWEI = 0.1
MAINNET_MAX_TEND_TIP_GWEI = 50.0
TEND_TIP_BUMP = 1.5
TEND_GIVE_UP_SECONDS = 3 * TEND_RETRY_SECONDS
REPLACE_FEE_STEP = 1.15  # nodes reject a replacement unless both fees rise at least 10%

PROCESS_REPORT_HOURS_UTC = (3, 7)  # mainnet only
REPORTING_MANAGER = 32
DEBT_MANAGER = 64

FLASHBOTS_TX_URL = "https://protect.flashbots.net/tx/"


@dataclass
class _Tend:
    strategy: str
    nonce: int
    tip_gwei: float
    max_fee_gwei: float
    first_ts: float
    sent_ts: float
    hashes: list[str] = field(default_factory=list)
    active: bool = True  # False once given up; its tx may still be pending, so its fees stay the floor at its nonce


# The tend signer's last unmined tend; bumps replace it at the same nonce
_inflight_tend: _Tend | None = None

# Set when a harvest tx is stuck; the rest of the sweep doesn't send
_harvest_blocked = False

# Strategies kept through our relayers, found by the last sweep; the tend loop watches them
_kept_strategies: list[str] = []

# Keeper activity since the last digest
_stats: dict[str, float] = {}


# =============================================================================
# Helpers
# =============================================================================


def strategy_name(w3: Web3, address: str) -> str:
    try:
        return html.escape(str(w3_contract(w3, address, TOKENIZED_STRATEGY_ABI).functions.name().call()))
    except Exception:
        return f"{address[:6]}…{address[-4:]}"


def _net() -> str:
    return network().capitalize()


def _addr_link(address: str, label: str = "🔗 View Strategy") -> str:
    return f"<a href='{explorer_base_url()}{address}'>{label}</a>"


def _tx_link(tx_hash: str) -> str:
    return f"<a href='{explorer_base_url().replace('/address/', '/tx/')}{tx_hash}'>🔗 View Transaction</a>"


def _private() -> bool:
    return bool(private_rpc_url())


def _receipt_timeout() -> int:
    # Flashbots Protect keeps a private tx pending for up to 6 minutes
    return 370 if _private() else 120


def _dedupe(addrs: list[str]) -> list[str]:
    return list(dict.fromkeys(Web3.to_checksum_address(a) for a in addrs))


def _reason(e: Exception) -> str:
    # ContractLogicError carries the readable revert in .message; str(e) adds the raw revert data
    return html.escape(str(getattr(e, "message", None) or e))


def _count(key: str, amount: float = 1) -> None:
    _stats[key] = _stats.get(key, 0) + amount


def _base_fee_gwei(w3: Web3) -> float:
    return float(w3.eth.get_block("latest")["baseFeePerGas"]) / 1e9


def _node_tip_gwei(w3: Web3) -> float:
    return float(w3.eth.max_priority_fee) / 1e9


async def _warn_once(key: str, msg: str, chat_id: int | None = None) -> None:
    state = load_state()
    alerts = state.setdefault("keeper_alerts_ts", {})
    now_ts = int(time.time())
    if now_ts - alerts.get(key, 0) < WARN_COOLDOWN_SECONDS:
        return
    alerts[key] = now_ts
    save_state(state)
    if chat_id is None:
        await notify_group_chat(msg)
    else:
        await notify_group_chat(msg, chat_id=chat_id)


# =============================================================================
# Relayers
# =============================================================================


def _relayer_for(w3: Web3, keeper_addr: str | None) -> Contract | None:
    if not keeper_addr:
        return None
    for addr in relayer_addrs():
        if addr.lower() == keeper_addr.lower():
            return w3_contract(w3, addr, RELAYER_ABI)
    if keeper_addr.lower() == PERMISSIONLESS_RELAYER.lower():
        return w3_contract(w3, PERMISSIONLESS_RELAYER, PERMISSIONLESS_RELAYER_ABI)
    return None


def _is_permissionless(relayer: Contract) -> bool:
    return relayer.address.lower() == PERMISSIONLESS_RELAYER.lower()


def _usable_relayers(w3: Web3, signer: str | None) -> set[str]:
    """Lowercased relayers the signer can call: the permissionless one plus TKSRelayers that list it as keeper."""
    relayers = relayer_addrs()
    if signer is None:
        return {PERMISSIONLESS_RELAYER.lower()} | {r.lower() for r in relayers}
    results = multicall(
        w3, [w3_contract(w3, r, RELAYER_ABI).functions.keepers(signer) for r in relayers], allow_failure=True
    )
    return {PERMISSIONLESS_RELAYER.lower()} | {r.lower() for r, ok in zip(relayers, results) if ok}


def _tend_call(relayer: Contract, strategy: str) -> ContractFunction:
    if _is_permissionless(relayer):
        return relayer.functions.tend(strategy)
    return relayer.functions.tendStrategy(strategy)


def _report_call(relayer: Contract, strategy: str) -> ContractFunction:
    if _is_permissionless(relayer):
        return relayer.functions.report(strategy)
    return relayer.functions.harvestStrategy(strategy)


def _process_report_call(relayer: Contract, vault: str, strategy: str) -> ContractFunction:
    if _is_permissionless(relayer):
        return relayer.functions.process_report(vault, strategy)
    return relayer.functions.processReport(vault, strategy)


# =============================================================================
# Tends (tend signer, every TEND_CHECK_INTERVAL)
# =============================================================================


async def check_tend_triggers(bot: TinyBot) -> None:
    # Hand-listed strategies (any keeper) plus every strategy kept by our relayers, found by the sweep
    candidates = _dedupe(all_strategy_addrs() + _kept_strategies)
    if not candidates:
        return

    w3 = bot.w3
    inflight = await _settle_tend(bot)
    calls = [w3_contract(w3, addr, BASE_STRATEGY_ABI).functions.tendTrigger() for addr in candidates]
    results = multicall(w3, calls, allow_failure=True)
    triggered = [addr for addr, result in zip(candidates, results) if result and result[0]]
    now_ts = time.time()

    # The in-flight tend still needs to land: bump it once per retry, give up after a few.
    # Another tend would replace it at the same nonce, so the others only get alerted meanwhile.
    if inflight is not None and inflight.active and inflight.strategy in triggered:
        if now_ts - inflight.first_ts > TEND_GIVE_UP_SECONDS:
            await _give_up_tend(bot, f"not mined after {TEND_GIVE_UP_SECONDS // 60} minutes")
        elif now_ts - inflight.sent_ts >= TEND_RETRY_SECONDS:
            await _tend(bot, inflight.strategy)
        if _inflight_tend is not None and _inflight_tend.active:
            for addr in triggered:
                if addr != _inflight_tend.strategy:
                    note = "<i>Waiting for another tend to land first...</i>"
                    await _needs_tending_alert(bot, addr, note, state_key="tend_wait_alerts_ts")
            return

    last_attempts = load_state().get("tend_alerts_ts", {})
    for addr in triggered:
        if now_ts - last_attempts.get(addr, 0) < TEND_RETRY_SECONDS:
            continue
        if await _tend(bot, addr):
            return  # one tend in flight at a time


async def _settle_tend(bot: TinyBot) -> _Tend | None:
    """Clear the in-flight tend once its nonce is mined, alerting if it reverted."""
    global _inflight_tend
    tend = _inflight_tend
    if tend is None or bot.executor is None:
        return tend
    if bot.w3.eth.get_transaction_count(bot.executor.address, "latest") <= tend.nonce:
        return tend

    _inflight_tend = None
    for tx_hash in reversed(tend.hashes):
        try:
            receipt = bot.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            continue
        _count("tend")
        _count("gas_wei", receipt["gasUsed"] * receipt["effectiveGasPrice"])
        if receipt["status"] == 0:
            _count("reverted")
            await notify_group_chat(
                f"❌ <b>Keeper tx reverted</b>\n\n"
                f"<b>Action:</b> tend\n"
                f"<b>Name:</b> {strategy_name(bot.w3, tend.strategy)}\n"
                f"<b>Network:</b> {_net()}\n\n"
                f"{_tx_link(tx_hash)}"
            )
        break
    return None


async def _give_up_tend(bot: TinyBot, reason: str) -> None:
    """Stop pushing the in-flight tend so other tends can go out; it retries after TEND_RETRY_SECONDS."""
    tend = _inflight_tend
    if tend is None:
        return
    tend.active = False
    state = load_state()
    state.setdefault("tend_alerts_ts", {})[tend.strategy] = int(time.time())
    save_state(state)
    await _warn_once(
        f"tend-stuck:{tend.strategy}",
        f"⚠️ <b>Tend not landing</b>\n\n"
        f"<b>Name:</b> {strategy_name(bot.w3, tend.strategy)}\n"
        f"<b>Reason:</b> {html.escape(reason)}\n"
        f"<b>Tip:</b> {tend.tip_gwei:.2f} gwei\n"
        f"<b>Network:</b> {_net()}\n\n"
        f"{_tx_link(tend.hashes[-1])}",
    )


async def _needs_tending_alert(bot: TinyBot, strategy: str, note: str, state_key: str = "tend_alerts_ts") -> None:
    """The 🚨 alert for a strategy that needs a tend, at most once per TEND_RETRY_SECONDS."""
    state = load_state()
    attempts = state.setdefault(state_key, {})
    now_ts = int(time.time())
    if now_ts - attempts.get(strategy, 0) < TEND_RETRY_SECONDS:
        return
    attempts[strategy] = now_ts
    save_state(state)
    await notify_group_chat(
        f"🚨 <b>Strategy needs tending!</b>\n\n"
        f"<b>Name:</b> {strategy_name(bot.w3, strategy)}\n"
        f"<b>Network:</b> {_net()}\n\n"
        f"{note}\n"
        f"<i>Sleeping for {int(TEND_RETRY_SECONDS / 60)} minutes...</i>\n\n"
        f"{_addr_link(strategy)}"
    )


async def _tend(bot: TinyBot, strategy: str) -> bool:
    """Send (or bump) a tend. Returns True if a tend is now in flight."""
    global _inflight_tend
    w3 = bot.w3
    inflight = _inflight_tend
    is_bump = inflight is not None and inflight.active and inflight.strategy == strategy
    name = strategy_name(w3, strategy)

    try:
        keeper_addr = w3_contract(w3, strategy, TOKENIZED_STRATEGY_ABI).functions.keeper().call()
    except Exception:
        keeper_addr = None
    relayer = _relayer_for(w3, keeper_addr)
    executor = bot.executor

    if not is_bump:
        if relayer is None:
            note = f"<i>Its keeper {keeper_addr} isn't one of our relayers, not tending.</i>"
        elif executor is None:
            note = "<i>No tend signer configured, not tending.</i>"
        else:
            note = "<i>Attempting to tend...</i>"
        await _needs_tending_alert(bot, strategy, note)

    if relayer is None or executor is None:
        return False

    if relayer.address.lower() not in _usable_relayers(w3, executor.address):
        await _warn_once(
            f"tend-relayer:{relayer.address}",
            f"⚠️ <b>Tend signer isn't a keeper on a relayer</b>\n\n"
            f"<b>Signer:</b> {executor.address}\n"
            f"<b>Network:</b> {_net()}\n\n"
            f"<i>Tends through this relayer are skipped until setKeeper is called.</i>\n\n"
            f"{_addr_link(relayer.address, '🔗 View Relayer')}",
        )
        return False

    nonce = w3.eth.get_transaction_count(executor.address, "latest")
    if inflight is not None and nonce > inflight.nonce:
        await _settle_tend(bot)  # it landed since the last check
        if is_bump:
            return False
        inflight = None

    # Fees: a tx may still be pending at this nonce, so outbid it; a bump also escalates the tip
    start_tip = MAINNET_TEND_TIP_GWEI if network() == "ethereum" else max(_node_tip_gwei(w3), MIN_TEND_TIP_GWEI)
    max_tip = MAINNET_MAX_TEND_TIP_GWEI if network() == "ethereum" else start_tip * 10
    tip = start_tip
    max_fee = 0.0
    if inflight is not None:
        tip = max(tip, inflight.tip_gwei * (TEND_TIP_BUMP if is_bump else REPLACE_FEE_STEP))
        max_fee = inflight.max_fee_gwei * REPLACE_FEE_STEP
        if is_bump and tip > max_tip:
            await _give_up_tend(bot, f"tip reached the {max_tip:.2f} gwei cap")
            return False
    max_fee = max(max_fee, _base_fee_gwei(w3) * 2 + tip)

    try:
        tx_hash = executor.execute(
            _tend_call(relayer, strategy),
            max_fee_gwei=max_fee,
            max_priority_fee_gwei=tip,
            wait=0,
            private=_private(),
            replace_pending=True,
        )
    except ContractLogicError as e:
        if is_bump:
            # The pending tend would revert too
            await _give_up_tend(bot, f"tend now reverts: {_reason(e)}")
            return False
        # At most once per TEND_RETRY_SECONDS, since the attempt was recorded above
        await notify_group_chat(
            f"❌ <b>Tend failed</b>\n\n"
            f"<b>Name:</b> {name}\n"
            f"<b>Reason:</b> {_reason(e)}\n"
            f"<b>Network:</b> {_net()}\n\n"
            f"{_addr_link(strategy)}"
        )
        return False
    except Exception as e:
        await _warn_once(f"tend-send:{strategy}", f"❌ [tend] {name}: {html.escape(str(e))}", chat_id=DEV_GROUP_CHAT_ID)
        return False

    now_ts = time.time()
    if inflight is not None and inflight.nonce == nonce:
        if not is_bump:
            inflight.first_ts = now_ts
        inflight.strategy = strategy
        inflight.tip_gwei = tip
        inflight.max_fee_gwei = max_fee
        inflight.sent_ts = now_ts
        inflight.active = True
        inflight.hashes.append(tx_hash)
    else:
        _inflight_tend = _Tend(
            strategy=strategy,
            nonce=nonce,
            tip_gwei=tip,
            max_fee_gwei=max_fee,
            first_ts=now_ts,
            sent_ts=now_ts,
            hashes=[tx_hash],
        )

    if is_bump:
        await notify_group_chat(
            f"⛽ Tend bumped to {tip:.2f} gwei — <b>{name}</b> on {_net()}\n{_tx_link(tx_hash)}",
            chat_id=DEV_GROUP_CHAT_ID,
        )
    else:
        await notify_group_chat(
            f"✅ <b>Tend tx submitted</b>\n\n<b>Name:</b> {name}\n<b>Network:</b> {_net()}\n\n{_tx_link(tx_hash)}"
        )
    return True


# =============================================================================
# Keeper sweep (harvest signer, every keeper_interval)
# =============================================================================


async def _send(bot: TinyBot, call: ContractFunction, action: str, label: str, key: str) -> None:
    """Send one keeper tx from the harvest signer and wait for it, alerting on failure."""
    global _harvest_blocked
    w3 = bot.w3
    executor = bot.executors.get("harvest")
    if executor is None or _harvest_blocked:
        return

    # Sweeps can run for minutes; don't let tends wait behind them
    await check_tend_triggers(bot)
    if action == "report" and _inflight_tend is not None and _inflight_tend.active and _inflight_tend.strategy == key:
        return  # don't report on top of a pending tend

    tip = _node_tip_gwei(w3)
    max_fee = _base_fee_gwei(w3) * 2 + tip
    try:
        tx_hash = executor.execute(call, max_fee_gwei=max_fee, max_priority_fee_gwei=tip, wait=0, private=_private())
    except ContractLogicError as e:
        await _warn_once(
            f"{action}:{key}",
            f"⚠️ <b>Keeper skipped {action}</b>\n\n"
            f"<b>Name:</b> {label}\n"
            f"<b>Reason:</b> {_reason(e)}\n"
            f"<b>Network:</b> {_net()}\n\n"
            f"{_addr_link(key)}",
        )
        return
    except Exception as e:
        await _warn_once(
            f"send:{action}:{key}",
            f"❌ [keeper {action}] {label}: {html.escape(str(e))}",
            chat_id=DEV_GROUP_CHAT_ID,
        )
        return

    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=_receipt_timeout())
    except TimeExhausted:
        # Later txs would only queue behind it; stop sending until the next sweep
        _harvest_blocked = True
        _count("not_mined")
        status_link = f"\n<a href='{FLASHBOTS_TX_URL}{tx_hash}'>🔗 Flashbots Status</a>" if _private() else ""
        await _warn_once(
            f"not-mined:{action}:{key}",
            f"⏳ <b>Keeper tx not mined</b>\n\n"
            f"<b>Action:</b> {action}\n"
            f"<b>Name:</b> {label}\n"
            f"<b>Network:</b> {_net()}\n\n"
            f"<i>Pausing keeper txs until it clears.</i>\n\n"
            f"{_tx_link(tx_hash)}{status_link}",
        )
        return

    _count(action)
    _count("gas_wei", receipt["gasUsed"] * receipt["effectiveGasPrice"])
    if receipt["status"] == 0:
        _count("reverted")
        await notify_group_chat(
            f"❌ <b>Keeper tx reverted</b>\n\n"
            f"<b>Action:</b> {action}\n"
            f"<b>Name:</b> {label}\n"
            f"<b>Network:</b> {_net()}\n\n"
            f"{_tx_link(tx_hash)}"
        )


async def run_keeper(bot: TinyBot) -> None:
    global _kept_strategies, _harvest_blocked
    w3 = bot.w3
    skip = {addr.lower() for addr in keeper_skip_addrs()}
    harvester = bot.executors.get("harvest")
    # A harvest tx still in the mempool (public chains) would make every send this sweep queue behind it
    _harvest_blocked = harvester is not None and w3.eth.get_transaction_count(
        harvester.address, "pending"
    ) > w3.eth.get_transaction_count(harvester.address, "latest")
    usable = _usable_relayers(w3, harvester.address if harvester else None)
    for relayer in relayer_addrs():
        if relayer.lower() not in usable and harvester is not None:
            await _warn_once(
                f"harvest-relayer:{relayer}",
                f"⚠️ <b>Harvest signer isn't a keeper on a relayer</b>\n\n"
                f"<b>Signer:</b> {harvester.address}\n"
                f"<b>Network:</b> {_net()}\n\n"
                f"<i>Reports and debt updates through this relayer are skipped until setKeeper is called.</i>\n\n"
                f"{_addr_link(relayer, '🔗 View Relayer')}",
            )

    # Vaults: endorsed in the registries, plus keeper_include, minus keeper_skip
    registries = [w3_contract(w3, addr, REGISTRY_ABI) for addr in REGISTRY_ADDRESSES]
    endorsed = multicall(w3, [r.functions.getAllEndorsedVaults() for r in registries], allow_failure=True)
    vaults = _dedupe([v for result in endorsed if result for group in result for v in group] + keeper_include_addrs())
    vaults = [v for v in vaults if v.lower() not in skip]

    # Allocator vaults answer get_default_queue(); strategies revert
    queues = multicall(
        w3, [w3_contract(w3, v, VAULT_ABI).functions.get_default_queue() for v in vaults], allow_failure=True
    )
    allocators = {v: _dedupe(list(q) + keeper_extra_strategies(v)) for v, q in zip(vaults, queues) if q is not None}
    strategies = _dedupe(
        [v for v, q in zip(vaults, queues) if q is None] + [s for qs in allocators.values() for s in qs]
    )
    strategies = [s for s in strategies if s.lower() not in skip]

    if harvester is None:
        # Tend-only instance: just find our strategies for the tend loop
        keepers = multicall(
            w3, [w3_contract(w3, s, TOKENIZED_STRATEGY_ABI).functions.keeper() for s in strategies], allow_failure=True
        )
        _kept_strategies = [s for s, k in zip(strategies, keepers) if _relayer_for(w3, k) is not None]
        return

    crt = w3_contract(w3, COMMON_REPORT_TRIGGER, COMMON_REPORT_TRIGGER_ABI)
    try:
        base_fee_ok = bool(crt.functions.isCurrentBaseFeeAcceptable().call())
    except Exception:
        base_fee_ok = False
    block_ts = int(w3.eth.get_block("latest")["timestamp"])
    hour = datetime.fromtimestamp(block_ts, tz=timezone.utc).hour
    in_window = network() != "ethereum" or PROCESS_REPORT_HOURS_UTC[0] <= hour < PROCESS_REPORT_HOURS_UTC[1]

    # Read everything up front in a few multicalls; the loop below only sends
    debt_updates = _plan_debt_updates(w3, allocators, skip, usable) if base_fee_ok else {}
    process_reports = _plan_process_reports(w3, allocators, usable) if in_window else {}

    for vault in allocators:
        try:
            if vault in debt_updates:
                await _update_debt(bot, vault, *debt_updates[vault])
            if vault in process_reports:
                await _process_reports(bot, vault, *process_reports[vault])
        except Exception as e:
            _count("errors")
            print(f"[keeper] vault {vault} failed: {e}")

    _kept_strategies = await _report_strategies(bot, strategies, usable, block_ts)


def _plan_debt_updates(
    w3: Web3, allocators: dict[str, list[str]], skip: set[str], usable: set[str]
) -> dict[str, tuple[str, str, list[tuple[str, bytes, int]]]]:
    """vault -> (debt allocator, relayer, [(strategy, calldata, debt delta)]) for vaults with debt to move."""
    vaults = list(allocators)
    role_managers = multicall(
        w3, [w3_contract(w3, v, VAULT_ABI).functions.role_manager() for v in vaults], allow_failure=True
    )
    managers = _dedupe([rm for rm in role_managers if rm])
    # getDebtAllocator reverts on role managers without one (e.g. Safes)
    results = multicall(
        w3, [w3_contract(w3, rm, ROLE_MANAGER_ABI).functions.getDebtAllocator() for rm in managers], allow_failure=True
    )
    allocator_of = {
        rm.lower(): Web3.to_checksum_address(da) for rm, da in zip(managers, results) if da and int(da, 16) != 0
    }
    vault_allocator = {
        v: allocator_of[rm.lower()] for v, rm in zip(vaults, role_managers) if rm and rm.lower() in allocator_of
    }
    if not vault_allocator:
        return {}

    # The allocator needs DEBT_MANAGER on the vault, and one of our usable relayers must be its keeper
    relayers = relayer_addrs()
    debt_allocators = _dedupe(list(vault_allocator.values()))
    keeper_calls = [
        w3_contract(w3, da, DEBT_ALLOCATOR_ABI).functions.keepers(r) for da in debt_allocators for r in relayers
    ]
    role_calls = [w3_contract(w3, v, VAULT_ABI).functions.roles(da) for v, da in vault_allocator.items()]
    results = multicall(w3, keeper_calls + role_calls, allow_failure=True)
    relayer_of: dict[str, str] = {}
    for i, da in enumerate(debt_allocators):
        is_keeper = results[i * len(relayers) : (i + 1) * len(relayers)]
        relayer = next((r for r, ok in zip(relayers, is_keeper) if ok and r.lower() in usable), None)
        if relayer is not None:
            relayer_of[da.lower()] = relayer
    eligible = {
        v: da
        for (v, da), roles in zip(vault_allocator.items(), results[len(keeper_calls) :])
        if roles and roles & DEBT_MANAGER and da.lower() in relayer_of
    }

    pairs = [(v, s) for v in eligible for s in allocators[v] if s.lower() not in skip]
    results = multicall(
        w3,
        [w3_contract(w3, eligible[v], DEBT_ALLOCATOR_ABI).functions.shouldUpdateDebt(v, s) for v, s in pairs]
        + [w3_contract(w3, v, VAULT_ABI).functions.strategies(s) for v, s in pairs],
        allow_failure=True,
    )
    plans: dict[str, tuple[str, str, list[tuple[str, bytes, int]]]] = {}
    for (v, s), should, info in zip(pairs, results[: len(pairs)], results[len(pairs) :]):
        if not should or not should[0] or info is None:
            continue
        _, _, new_debt = decode(["address", "address", "uint256"], should[1][4:])
        da = eligible[v]
        plans.setdefault(v, (da, relayer_of[da.lower()], []))[2].append((s, should[1], new_debt - info[2]))
    return plans


def _plan_process_reports(
    w3: Web3, allocators: dict[str, list[str]], usable: set[str]
) -> dict[str, tuple[str, list[str]]]:
    """vault -> (reporting relayer, [strategies whose vaultReportTrigger fired])."""
    vaults = list(allocators)
    reporters = relayer_addrs() + [PERMISSIONLESS_RELAYER]
    results = multicall(
        w3, [w3_contract(w3, v, VAULT_ABI).functions.roles(r) for v in vaults for r in reporters], allow_failure=True
    )
    reporter_of: dict[str, str] = {}
    for i, v in enumerate(vaults):
        roles = results[i * len(reporters) : (i + 1) * len(reporters)]
        reporter = next(
            (r for r, role in zip(reporters, roles) if role and role & REPORTING_MANAGER and r.lower() in usable),
            None,
        )
        if reporter is not None:
            reporter_of[v] = reporter

    crt = w3_contract(w3, COMMON_REPORT_TRIGGER, COMMON_REPORT_TRIGGER_ABI)
    pairs = [(v, s) for v in reporter_of for s in allocators[v]]
    triggers = multicall(w3, [crt.functions.vaultReportTrigger(v, s) for v, s in pairs], allow_failure=True)
    plans: dict[str, tuple[str, list[str]]] = {}
    for (v, s), trigger in zip(pairs, triggers):
        if trigger and trigger[0]:
            plans.setdefault(v, (reporter_of[v], []))[1].append(s)
    return plans


async def _update_debt(
    bot: TinyBot, vault: str, allocator_addr: str, relayer_addr: str, updates: list[tuple[str, bytes, int]]
) -> None:
    w3 = bot.w3
    allocator = w3_contract(w3, allocator_addr, DEBT_ALLOCATOR_ABI)
    relayer = w3_contract(w3, relayer_addr, RELAYER_ABI)
    harvester = bot.executors.get("harvest")
    vault_name = strategy_name(w3, vault)
    # Decreases first, so increases can use the freed funds
    for s, _, _ in sorted(updates, key=lambda u: u[2]):
        label = f"{vault_name} → {strategy_name(w3, s)}"
        # Earlier txs in this sweep move funds, so take fresh calldata right before sending
        ok, calldata = allocator.functions.shouldUpdateDebt(vault, s).call()
        if not ok:
            continue
        call = relayer.functions.forwardCall(allocator.address, calldata)
        # Deployed relayers return false instead of reverting when the allocator call fails
        if harvester is not None:
            try:
                forwarded = bool(call.call({"from": harvester.address}))
            except ContractLogicError:
                forwarded = False
            if not forwarded:
                await _warn_once(
                    f"debt update:{s}",
                    f"⚠️ <b>Keeper skipped debt update</b>\n\n"
                    f"<b>Name:</b> {label}\n"
                    f"<b>Reason:</b> the debt allocator's update_debt reverts\n"
                    f"<b>Network:</b> {_net()}\n\n"
                    f"{_addr_link(s)}",
                )
                continue
        await _send(bot, call, "debt update", label, s)


async def _process_reports(bot: TinyBot, vault: str, reporter: str, strategies: list[str]) -> None:
    w3 = bot.w3
    relayer = _relayer_for(w3, reporter)
    if relayer is None:
        return
    crt = w3_contract(w3, COMMON_REPORT_TRIGGER, COMMON_REPORT_TRIGGER_ABI)
    vault_name = strategy_name(w3, vault)
    for s in strategies:
        try:
            if not crt.functions.vaultReportTrigger(vault, s).call()[0]:
                continue  # an earlier tx in this sweep cleared it
        except Exception:
            continue
        label = f"{vault_name} → {strategy_name(w3, s)}"
        await _send(bot, _process_report_call(relayer, vault, s), "process_report", label, s)


async def _report_strategies(bot: TinyBot, strategies: list[str], usable: set[str], now_ts: int) -> list[str]:
    """Report strategies whose keeper is one of our relayers. Returns those strategies for the tend loop."""
    w3 = bot.w3
    crt = w3_contract(w3, COMMON_REPORT_TRIGGER, COMMON_REPORT_TRIGGER_ABI)
    calls = []
    for s in strategies:
        strategy = w3_contract(w3, s, TOKENIZED_STRATEGY_ABI)
        calls += [
            strategy.functions.keeper(),
            w3_contract(w3, s, BASE_STRATEGY_ABI).functions.tendTrigger(),
            strategy.functions.profitMaxUnlockTime(),
            strategy.functions.lastReport(),
            crt.functions.strategyReportTrigger(s),
        ]
    results = multicall(w3, calls, allow_failure=True)

    kept: list[str] = []
    for i, s in enumerate(strategies):
        keeper_addr, tend, unlock_time, last_report, report_trigger = results[i * 5 : i * 5 + 5]
        relayer = _relayer_for(w3, keeper_addr)
        if relayer is None:
            continue
        kept.append(s)
        try:
            if tend and tend[0]:
                continue  # the tend loop handles it; don't report on top of a tend
            if unlock_time is None or last_report is None:
                continue
            if unlock_time == 0 and now_ts - last_report < DAY_SECONDS:
                continue
            if not report_trigger or not report_trigger[0]:
                continue
            if relayer.address.lower() not in usable:
                continue
            if not crt.functions.strategyReportTrigger(s).call()[0]:
                continue
            try:
                profit, loss = (
                    w3_contract(w3, s, TOKENIZED_STRATEGY_ABI).functions.report().call({"from": relayer.address})
                )
            except ContractLogicError as e:
                await _warn_once(
                    f"report:{s}",
                    f"⚠️ <b>Keeper skipped report</b>\n\n"
                    f"<b>Name:</b> {strategy_name(w3, s)}\n"
                    f"<b>Reason:</b> {_reason(e)}\n"
                    f"<b>Network:</b> {_net()}\n\n"
                    f"{_addr_link(s)}",
                )
                continue
            if profit + loss == 0:
                continue
            await _send(bot, _report_call(relayer, s), "report", strategy_name(w3, s), s)
        except Exception as e:
            _count("errors")
            print(f"[keeper] strategy {s} failed: {e}")
    return kept


# =============================================================================
# Daily digest
# =============================================================================


async def report_keeper_digest(bot: TinyBot) -> None:
    global _stats
    stats, _stats = _stats, {}
    if not any(value for key, value in stats.items() if key != "gas_wei"):
        return

    lines = [f"🤖 <b>Keeper — {_net()}</b> (last 24h)\n"]
    for key, label in [
        ("debt update", "Debt updates"),
        ("process_report", "Process reports"),
        ("report", "Reports"),
        ("tend", "Tends"),
        ("reverted", "Reverted"),
        ("not_mined", "Not mined"),
        ("errors", "Errors"),
    ]:
        if stats.get(key):
            lines.append(f"<b>{label}:</b> {int(stats[key])}")
    lines.append(f"<b>Gas:</b> {stats.get('gas_wei', 0) / 1e18:.4f} ETH")
    await notify_group_chat("\n".join(lines))
