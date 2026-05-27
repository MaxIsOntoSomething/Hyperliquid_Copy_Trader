# Hyperliquid Copy Trader

<p align="center">
  <a href="https://hyperfoundation.org/" target="_blank">
    <img src="https://www.cryptoninjas.net/wp-content/uploads/hyperliquid-logo-330x330.webp" alt="Hyperliquid Logo" width="200"/>
  </a>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

Automated copy trading bot for Hyperliquid DEX. Copies trades from any wallet in real-time with automatic position sizing.

## Features

- Real-time trade copying via WebSocket
- Automatic position sizing based on account balance ratio
- Integer leverage with asset-specific limits
- Market and limit order support
- Copy existing positions on startup
- Simulated trading mode for testing
- Telegram notifications (optional)

## Quick Start

### Docker (Recommended)

```bash
docker-compose up -d
```

### Manual Installation

1. Install uv
2. Install dependencies:

```bash
uv sync
```

3. Configure .env file with your settings
4. Run the bot:

```bash
uv run python src/main.py
```

## Configuration

Edit the `.env` file:

```properties
# Hyperliquid API
HYPERLIQUID_API_URL=https://api.hyperliquid.xyz

# Your Hyperliquid credentials (leave empty for simulation)
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_PRIVATE_KEY=

# Target to copy (wallet or vault)
TARGET_WALLET_ADDRESS=0x...

# Trading mode
SIMULATED_TRADING=true
SIMULATED_ACCOUNT_BALANCE=10000.0

# Copy settings
COPY_OPEN_POSITIONS=true
COPY_EXISTING_ORDERS=true
AUTO_ADJUST_SIZE=true
USE_LIMIT_ORDERS=false
LEVERAGE_ADJUSTMENT=1.0
MAX_OPEN_TRADES=x
MAX_OPEN_ORDERS=x
MAX_ACCOUNT_EQUITY=x

# Asset Filters
BLOCKED_ASSETS=BTC,ETH  # Comma-separated list (e.g., BTC,ETH,SOL)

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database
DATABASE_URL=sqlite:///./data/trading.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/trading.log
```

Notes:

- `TARGET_WALLET_ADDRESS` accepts either a wallet address or a vault address.
- `x` means unlimited; set an integer to cap `MAX_OPEN_TRADES`, `MAX_OPEN_ORDERS`, or `MAX_ACCOUNT_EQUITY`.
- Hyperliquid enforces a $10 minimum notional per order. If your account is much smaller than the target, small fills will be skipped when the proportional size falls below $10. Increase balance or reduce the ratio gap to copy more trades.

## Leverage Adjustment

The `LEVERAGE_ADJUSTMENT` setting controls risk:

- 0.5 = Use 50% of target's leverage (safer)
- 1.0 = Match target's leverage exactly
- 2.0 = Use 200% of target's leverage (more aggressive)

Leverage is automatically rounded to integers and capped at asset-specific maximums.

## Blocked Assets

The `BLOCKED_ASSETS` setting lets you exclude specific assets from copying:

```properties
BLOCKED_ASSETS=BTC,ETH,SOL
```

When the target wallet trades these assets, the bot will:

- Log a warning message
- Skip copying the trade
- Continue monitoring other assets normally

This is useful for:

- Avoiding high-volatility assets
- Excluding assets you're manually trading
- Managing risk by limiting exposure to certain markets

Note: Asset symbols are case-insensitive (BTC, btc, Btc all work).

## Position Sizing

Position sizes are automatically calculated based on the ratio of your account balance to the target wallet balance.

Example:

- Target wallet: $100,000
- Your account: $10,000
- Ratio: 1:10
- Target opens 1 BTC position = You open 0.1 BTC position

## Docker Commands

### Windows

Use the batch files in the `windows/` folder:

```cmd
cd windows
start.bat    # Start the bot
logs.bat     # View logs
stop.bat     # Stop the bot
```

### Linux/Mac

Use the shell scripts in the `linux/` folder:

```bash
cd linux
chmod +x *.sh       # Make executable (first time only)
./start.sh          # Start the bot
./logs.sh           # View logs
./stop.sh           # Stop the bot
```

### Manual Docker Commands

Start bot:

```bash
docker-compose up -d
```

View logs:

```bash
docker-compose logs -f
```

Stop bot:

```bash
docker-compose down
```

Rebuild after code changes:

```bash
docker-compose up -d --build
```

## Telegram Bot

To enable Telegram notifications:

1. Create bot with @BotFather on Telegram
2. Get your bot token
3. Send a message to your bot
4. Get your chat ID from: https://api.telegram.org/bot `<TOKEN>`/getUpdates
5. Add both values to .env file

Available commands:

- /status - Bot status and balance
- /positions - Current positions
- /pnl - Profit and loss report
- /pause - Pause copying
- /resume - Resume copying

## Disclaimer

Trading cryptocurrencies involves substantial risk of loss. This software is provided as-is without any warranties. Use at your own risk. The author is not responsible for any financial losses.

## Support

Discord: maskiplays

## Donations

If you find this bot useful, donations are appreciated:

Arbitrum USDC: 0x2987F53372c02D1a4C67241aA1840C1E83c480fF
Dont look at PNL :(

## Final Thoughts

10/10 Crash fucking sucked
Hyperliquid.
