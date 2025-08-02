# lender-borrower-monitor

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/johnnyonline/lender-borrower-monitor.git
   cd lender-borrower-monitor
   ```

2. **Set up virtual environment**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   # Install all dependencies
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

## Usage

Run:
```shell
silverback run src.bot:bot --network :mainnet
```

Run using docker compose:
```shell
docker compose up -d
```

Stop docker compose:
```shell
docker compose down
```

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
mypy .
```

## Add a new Strategy

TODO