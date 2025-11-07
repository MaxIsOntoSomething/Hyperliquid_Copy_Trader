# Hyperliquid Copy Trader

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

1. Install Python 3.12+

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure .env file with your settings

4. Run the bot:
```bash
python src/main.py
```

## Configuration

Edit the `.env` file:

```properties
# Target wallet to copy
TARGET_WALLET_ADDRESS=0x...

# Your Hyperliquid credentials (leave empty for simulation)
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_PRIVATE_KEY=

# Trading mode
SIMULATED_TRADING=true
SIMULATED_ACCOUNT_BALANCE=10000.0

# Copy settings
COPY_OPEN_POSITIONS=true
LEVERAGE_ADJUSTMENT=1.0
USE_LIMIT_ORDERS=false

# Asset Filters
BLOCKED_ASSETS=BTC,ETH  # Comma-separated list (e.g., BTC,ETH,SOL)

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

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
4. Get your chat ID from: https://api.telegram.org/bot<TOKEN>/getUpdates
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
