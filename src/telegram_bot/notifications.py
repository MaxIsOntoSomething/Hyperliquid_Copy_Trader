import asyncio
from typing import Optional
from datetime import datetime
from telegram import Bot
from loguru import logger


class NotificationService:
    """
    Service for sending Telegram notifications
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize notification service
        
        Args:
            bot_token: Telegram bot token
            chat_id: Chat ID to send notifications to
        """
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.enabled = True
        
        logger.info(f"Notification service initialized for chat {chat_id}")
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat"""
        if not self.enabled:
            logger.debug("Notifications disabled, skipping message")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        leverage: float,
        target_size: float,
        is_simulated: bool = True
    ):
        """Send notification about a copied trade"""
        
        mode_emoji = "🧪" if is_simulated else "✅"
        mode_text = "[SIMULATED]" if is_simulated else ""
        
        message = f"""
{mode_emoji} <b>New Trade Copied!</b> {mode_text}

<b>Symbol:</b> {symbol}
<b>Side:</b> {side.upper()}
<b>Your Size:</b> {size:.4f}
<b>Entry:</b> ${entry_price:,.2f}
<b>Leverage:</b> {leverage}x
<b>Notional:</b> ${size * entry_price:,.2f}

━━━━━━━━━━━━━━━━━━
<b>Target Size:</b> {target_size:.4f}
<b>Time:</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())
    
    async def send_position_close_notification(
        self,
        symbol: str,
        pnl: Optional[float] = None,
        is_simulated: bool = True
    ):
        """Send notification about a closed position"""
        
        mode_emoji = "🧪" if is_simulated else "🔴"
        mode_text = "[SIMULATED]" if is_simulated else ""
        
        pnl_text = ""
        if pnl is not None:
            pnl_emoji = "📈" if pnl > 0 else "📉"
            pnl_text = f"\n<b>PnL:</b> {pnl_emoji} ${pnl:,.2f}"
        
        message = f"""
{mode_emoji} <b>Position Closed</b> {mode_text}

<b>Symbol:</b> {symbol}{pnl_text}
<b>Time:</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())
    
    async def send_hourly_report(
        self,
        trades_copied: int,
        account_pnl_usd: float,
        account_pnl_pct: float,
        open_positions: int,
        open_orders: int,
        target_wallet: str
    ):
        """Send hourly trading report"""
        
        pnl_emoji = "📈" if account_pnl_usd > 0 else "📉"
        
        message = f"""
📊 <b>Hourly Copy Trading Report</b>

<b>Target:</b> <code>{target_wallet[:10]}...{target_wallet[-6:]}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>Trades Copied:</b> {trades_copied}
💰 <b>Account PnL:</b> {pnl_emoji} ${account_pnl_usd:,.2f} ({account_pnl_pct:+.2f}%)
📍 <b>Open Positions:</b> {open_positions}
📝 <b>Open Orders:</b> {open_orders}
━━━━━━━━━━━━━━━━━━━━━━━━━

🕐 <b>Report Time:</b> {datetime.now().strftime('%H:%M UTC')}
"""
        await self.send_message(message.strip())
    
    async def send_error_notification(self, error_message: str):
        """Send error notification"""
        message = f"""
⚠️ <b>Error Detected</b>

<code>{error_message}</code>

<b>Time:</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())
    
    async def send_startup_notification(
        self,
        target_wallet: str,
        sizing_mode: str,
        ratio: str,
        leverage_adjustment: float
    ):
        """Send bot startup notification"""
        message = f"""
🚀 <b>Copy Trading Bot Started</b>

<b>Target Wallet:</b>
<code>{target_wallet}</code>

<b>Configuration:</b>
• Sizing: {sizing_mode.title()}
• Ratio: {ratio}
• Leverage: {leverage_adjustment}x of target
• Status: <b>ACTIVE</b> 🟢

Bot is now monitoring for trades!
"""
        await self.send_message(message.strip())
    
    async def send_shutdown_notification(self):
        """Send bot shutdown notification"""
        message = """
🛑 <b>Copy Trading Bot Stopped</b>

Bot has been shut down gracefully.
Status: <b>INACTIVE</b> 🔴
"""
        await self.send_message(message.strip())
    
    def enable(self):
        """Enable notifications"""
        self.enabled = True
        logger.info("Notifications enabled")
    
    def disable(self):
        """Disable notifications"""
        self.enabled = False
        logger.info("Notifications disabled")
