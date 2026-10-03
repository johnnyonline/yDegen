# 👩‍🍼 vaults-mommy

Takes care of Yearn v3 vaults, like a mommy takes care of her kids: tends them when they need it, harvests and reports them on time, moves their debt around, and tells you when something's wrong.

One process per chain: ethereum, arbitrum, base, katana, optimism.

## What it does

A vault or strategy is **ours** when its keeper is one of our relayers: the TKSRelayer contracts listed under `relayers` in `bot/config.py`, or Yearn's permissionless relayer. The bot only acts on vaults and strategies that are ours.

**Keeping** (`bot/keeper.py`). Every `keeper_interval` seconds it sweeps every vault endorsed in the Yearn registries, plus `keeper_include`, minus `keeper_skip`, and:
- **Debt updates:** asks each allocator vault's DebtAllocator whether debt should move, and moves it through our relayer.
- **Process reports:** calls `process_report` on allocator vaults when `vaultReportTrigger` fires. On mainnet only between 03:00 and 07:00 UTC.
- **Reports:** harvests our strategies when `strategyReportTrigger` fires and the report would book a profit or loss.

**Tending** (`bot/keeper.py`). Every 60 seconds it checks `tendTrigger` on our strategies and on the hand-listed ones in `bot/config.py`, and tends the ones that need it. A tend that hasn't landed is retried every 10 minutes at the same nonce with a 1.5x higher tip, up to 50 gwei on mainnet.

Mainnet txs go through Flashbots Protect. Tends come from the tend signer and everything else from the harvest signer, so a slow harvest never holds up a tend.

**Monitoring** (`bot/monitor.py`):
- Alerts when any strategy needs a tend, and whether the tend went out.
- Daily status report at 08:00 UTC for the hand-listed strategies, plus a keeper digest: actions taken, reverts, gas spent.
- Deposit, withdraw and report events for `allocator_vaults`.
- Low gas balance alerts for both signers and `keepers`.
- `/status` and `/exposure` Telegram commands (ethereum process only).

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/johnnyonline/vaults-mommy.git
   cd vaults-mommy
   ```

2. **Set up virtual environment**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   uv sync
   ```

   > Note: This project uses [uv](https://github.com/astral-sh/uv) for faster dependency installation. If you don't have uv installed, you can install it with `pip install uv` or follow the [installation instructions](https://github.com/astral-sh/uv#installation).

4. **Environment setup**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration

   # Load environment variables into your shell session
   export $(grep -v '^#' .env | xargs)
   ```

## Configuration

| Variable | |
|---|---|
Every feature turns on with its own variables; leave them unset to turn it off.

| Variable | |
|---|---|
| `ETH_RPC_URL`, `ARB_RPC_URL`, `BASE_RPC_URL`, `KATANA_RPC_URL`, `OP_RPC_URL` | RPC per chain. The only required one. |
| `TEND_PRIVATE_KEY` | Tend signer. Must be a keeper on our relayers. Unset: no tends. |
| `HARVEST_PRIVATE_KEY` | Harvest signer for reports, process reports and debt updates. Must be a keeper on our relayers. Unset: no keeping beyond tends. |
| `BOT_ACCESS_TOKEN`, `GROUP_CHAT_ID`, `DEV_GROUP_CHAT_ID` | Telegram alerts, reports and commands. Unset: no Telegram at all. |
| `UPTIME_KUMA_HOST`, `UPTIME_KUMA_KEY_<CHAIN>` | Uptime Kuma push monitor per chain. Unset: no pings. |
| `TEND_CHECK_INTERVAL` | Seconds between tend checks (default 60). |
| `TEND_RETRY_SECONDS` | Wait between tend retries and repeated tend alerts (default 600). |
| `PRIVATE_RPC_URL` | Override the private relay (default Flashbots Protect on ethereum). Set empty to send publicly, e.g. against an anvil fork. |

Per-chain lists live in `bot/config.py`:
- To get status reports and tend alerts for a strategy, add it to the matching list (`lender_borrowers`, `morpho_loopers`, ...).
- To make the bot keep something the registries don't list, add it to `keeper_include`.
- To make it leave something alone, add it to `keeper_skip`.

## Usage

Run:
```shell
python -u -m bot
```

Run using docker compose:
```shell
docker compose up --build
```

Stop docker compose:
```shell
docker compose down
```

### Running a backup

Anyone can run a backup that only tends, to cover for the main instance. Its `.env` needs just an RPC and a tend key:

```shell
ETH_RPC_URL=...
TEND_PRIVATE_KEY=...      # your own key; ask for it to be added as keeper on our relayers
TEND_CHECK_INTERVAL=1800  # check less often than the main instance, so it mostly tends what the main one missed
```

```shell
docker compose up -d --build eth-vaults-mommy
```

Use your own tend key: two instances sending from the same key replace each other's txs.

## Code Style

Format and lint code with ruff:
```bash
# Format code
ruff format .

# Lint code
ruff check .

# Fix fixable lint issues
ruff check --fix .
```

Type checking with mypy:
```bash
mypy bot
```
