import asyncio
from typing import Optional, Callable
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from loguru import logger


class TelegramBot:
    """
    Telegram bot for controlling and monitoring the copy trader
    """
    
    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: str
    ):
        """
        Initialize Telegram bot
        
        Args:
            bot_token: Telegram bot token from BotFather
            allowed_chat_id: Only this chat ID can control the bot
        """
        self.bot_token = bot_token
        self.allowed_chat_id = str(allowed_chat_id)
        self.app: Optional[Application] = None
        
        # Callbacks that main app can set
        self.on_stop_requested: Optional[Callable] = None
        self.on_pause_requested: Optional[Callable] = None
        self.on_resume_requested: Optional[Callable] = None
        self.get_status_callback: Optional[Callable] = None
        self.get_positions_callback: Optional[Callable] = None
        self.get_orders_callback: Optional[Callable] = None
        self.get_pnl_callback: Optional[Callable] = None
        
        logger.info(f"Telegram bot initialized for chat {allowed_chat_id}")
    
    def _check_authorized(self, update: Update) -> bool:
        """Check if user is authorized"""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.allowed_chat_id:
            logger.warning(f"Unauthorized access attempt from chat {user_chat_id}")
            return False
        return True
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        message = """
🤖 <b>Hyperliquid Copy Trading Bot</b>

<b>Available Commands:</b>

/status - Current bot status
/positions - View open positions  
/orders - View open orders
/pnl - Account PnL summary
/pause - Pause copying (keep positions)
/resume - Resume copying
/stop - Stop bot and close positions

<b>Status:</b> 🟢 Active
        """
        await update.message.reply_text(message.strip(), parse_mode="HTML")
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        if self.get_status_callback:
            try:
                status = await self.get_status_callback()
                await update.message.reply_text(status, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("Status callback not configured")
    
    async def _positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        if self.get_positions_callback:
            try:
                positions = await self.get_positions_callback()
                await update.message.reply_text(positions, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error getting positions: {e}")
                await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("📍 No positions callback configured")
    
    async def _orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /orders command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        if self.get_orders_callback:
            try:
                orders = await self.get_orders_callback()
                
                if not orders:
                    await update.message.reply_text("📋 No open orders")
                    return
                
                message = "<b>Open Orders</b>\n\n"
                for i, order in enumerate(orders, 1):
                    side = order.get('side', 'BUY').upper()
                    order_type = order.get('order_type', 'LIMIT').upper()
                    
                    message += f"<b>{i}. {order['symbol']} {side}</b>\n"
                    message += f"   Type: {order_type}\n"
                    message += f"   Size: {abs(order['size']):.4f}\n"
                    message += f"   Price: ${order['price']:,.2f}\n"
                    
                    if 'trigger_price' in order and order['trigger_price']:
                        message += f"   Trigger: ${order['trigger_price']:,.2f}\n"
                    
                    message += "\n"
                
                await update.message.reply_text(message.strip(), parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error getting orders: {e}")
                await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("📋 No orders callback configured")
    
    async def _pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        if self.on_pause_requested:
            try:
                await self.on_pause_requested()
                await update.message.reply_text(
                    "⏸️ <b>Bot Paused</b>\n\nNo new trades will be copied.\nExisting positions remain open.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error pausing: {e}")
                await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("Pause callback not configured")
    
    async def _resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        if self.on_resume_requested:
            try:
                await self.on_resume_requested()
                await update.message.reply_text(
                    "▶️ <b>Bot Resumed</b>\n\nCopying trades is now active!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error resuming: {e}")
                await update.message.reply_text(f"❌ Error: {e}")
        else:
            await update.message.reply_text("Resume callback not configured")
    
    async def _stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command - show confirmation"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("Close Positions", callback_data="stop_close"),
                InlineKeyboardButton("Keep Positions", callback_data="stop_keep")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="stop_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ <b>STOP COPY TRADING</b>\n\n"
            "This will:\n"
            "✅ Stop copying new trades\n"
            "✅ Cancel all open orders\n\n"
            "Do you want to close all positions too?",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if not self._check_authorized(update):
            await query.edit_message_text("⛔ Unauthorized")
            return
        
        if query.data == "stop_close":
            await query.edit_message_text(
                "🛑 <b>Stopping bot...</b>\n\n"
                "• Cancelling all orders\n"
                "• Closing all positions\n"
                "• Shutting down\n\n"
                "Please wait...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=True)
                    await query.edit_message_text(
                        "✅ <b>Bot Stopped</b>\n\n"
                        "All orders cancelled.\n"
                        "All positions closed.\n"
                        "Status: 🔴 INACTIVE",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Error: {e}")
        
        elif query.data == "stop_keep":
            await query.edit_message_text(
                "🛑 <b>Stopping bot...</b>\n\n"
                "• Cancelling all orders\n"
                "• Keeping positions open\n"
                "• Shutting down\n\n"
                "Please wait...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=False)
                    await query.edit_message_text(
                        "✅ <b>Bot Stopped</b>\n\n"
                        "All orders cancelled.\n"
                        "Positions kept open.\n"
                        "Status: 🔴 INACTIVE",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Error: {e}")
        
        elif query.data == "stop_cancel":
            await query.edit_message_text(
                "✅ Stop cancelled. Bot is still running.",
                parse_mode="HTML"
            )
    
    async def _pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl command"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        
        # TODO: Get actual PnL from database
        message = """
💰 <b>Account PnL Summary</b>

<b>Session:</b>
• Total Trades: 0
• Winners: 0
• Losers: 0
• Win Rate: 0%

<b>PnL:</b>
• Today: $0.00 (0%)
• This Week: $0.00 (0%)
• Total: $0.00 (0%)

🕐 <i>Updated: {}</i>
        """.format(datetime.now().strftime('%H:%M:%S UTC'))
        
        await update.message.reply_text(message.strip(), parse_mode="HTML")
    
    async def start(self):
        """Start the Telegram bot"""
        logger.info("Starting Telegram bot...")
        
        # Create application
        self.app = Application.builder().token(self.bot_token).build()
        
        # Add command handlers
        self.app.add_handler(CommandHandler("start", self._start_command))
        self.app.add_handler(CommandHandler("status", self._status_command))
        self.app.add_handler(CommandHandler("positions", self._positions_command))
        self.app.add_handler(CommandHandler("orders", self._orders_command))
        self.app.add_handler(CommandHandler("pause", self._pause_command))
        self.app.add_handler(CommandHandler("resume", self._resume_command))
        self.app.add_handler(CommandHandler("stop", self._stop_command))
        self.app.add_handler(CommandHandler("pnl", self._pnl_command))
        
        # Add callback query handler for buttons
        self.app.add_handler(CallbackQueryHandler(self._button_callback))
        
        # Start polling
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("✅ Telegram bot started and polling")
    
    async def stop(self):
        """Stop the Telegram bot"""
        if self.app:
            logger.info("Stopping Telegram bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")
