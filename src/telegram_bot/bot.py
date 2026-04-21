import asyncio
from typing import Optional, Callable
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from loguru import logger


class TelegramBot:
    """
    Telegram bot for controlling and monitoring the copy trader.
    Provides a full interactive menu UI with inline keyboard navigation.
    """

    def __init__(self, bot_token: str, allowed_chat_id: str):
        self.bot_token = bot_token
        self.allowed_chat_id = str(allowed_chat_id)
        self.app: Optional[Application] = None

        # Callbacks wired by main.py
        self.on_stop_requested: Optional[Callable] = None
        self.on_pause_requested: Optional[Callable] = None
        self.on_resume_requested: Optional[Callable] = None
        self.get_status_callback: Optional[Callable] = None
        self.get_positions_callback: Optional[Callable] = None
        self.get_raw_positions_callback: Optional[Callable] = None
        self.get_orders_callback: Optional[Callable] = None
        self.get_pnl_callback: Optional[Callable] = None
        self.get_target_state_callback: Optional[Callable] = None
        self.close_position_callback: Optional[Callable] = None
        self.refresh_target_callback: Optional[Callable] = None
        self.update_setting_callback: Optional[Callable] = None
        self.get_settings_callback: Optional[Callable] = None   # sync lambda
        self.get_pause_state_callback: Optional[Callable] = None  # sync lambda

        # Public URL of the Mini App (set from main.py)
        self.webapp_url: str = ""

        # State for multi-step text input flows
        self._awaiting_input: dict = {}  # chat_id -> {"action": str}

        logger.info(f"Telegram bot initialized for chat {allowed_chat_id}")

    # ─── Auth ────────────────────────────────────────────────────────────────

    def _check_authorized(self, update: Update) -> bool:
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.allowed_chat_id:
            logger.warning(f"Unauthorized access attempt from chat {user_chat_id}")
            return False
        return True

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _truncate(self, text: str, limit: int = 3900) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n\n<i>... (message truncated)</i>"

    async def _safe_edit(self, query, text: str, markup=None, parse_mode: str = "HTML"):
        """Edit a message, silently ignoring 'not modified' errors."""
        try:
            await query.edit_message_text(
                text,
                reply_markup=markup,
                parse_mode=parse_mode
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise

    # ─── Menu builders (return text + InlineKeyboardMarkup) ──────────────────

    async def _build_main_menu(self) -> tuple:
        paused = self.get_pause_state_callback() if self.get_pause_state_callback else False

        header = "🤖 <b>Hyperliquid Copy Bot</b>\n\n"
        if self.get_status_callback:
            try:
                status_text = await self.get_status_callback()
                # Keep only the first 5 meaningful lines for the dashboard header
                lines = [l for l in status_text.split('\n') if l.strip()][:5]
                header += '\n'.join(lines)
            except Exception as e:
                header += f"⚠️ Status unavailable: {e}"

        pause_label = "▶️ Resume" if paused else "⏸️ Pause"
        pause_data = "resume" if paused else "pause"

        keyboard = [
            [
                InlineKeyboardButton("📍 Positions", callback_data="positions"),
                InlineKeyboardButton("📝 Orders", callback_data="orders"),
            ],
            [
                InlineKeyboardButton("💰 PnL", callback_data="pnl"),
                InlineKeyboardButton("📊 Status", callback_data="status"),
            ],
            [
                InlineKeyboardButton("🎯 Target Wallet", callback_data="target"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            ],
            [InlineKeyboardButton(pause_label, callback_data=pause_data)],
        ]
        return self._truncate(header), InlineKeyboardMarkup(keyboard)

    async def _build_positions_menu(self) -> tuple:
        text = "📍 <b>Open Positions</b>\n\nNo open positions."
        keyboard_rows = []

        if self.get_positions_callback:
            try:
                text = await self.get_positions_callback()
            except Exception as e:
                text = f"❌ Error loading positions: {e}"

        if self.get_raw_positions_callback:
            try:
                positions = await self.get_raw_positions_callback()
                for pos in positions:
                    symbol = pos['symbol']
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            f"❌ Close {symbol}",
                            callback_data=f"pos_close:{symbol}"
                        )
                    ])
            except Exception:
                pass

        keyboard_rows.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="positions"),
            InlineKeyboardButton("◀ Back", callback_data="menu"),
        ])
        return self._truncate(text), InlineKeyboardMarkup(keyboard_rows)

    async def _build_orders_view(self) -> tuple:
        keyboard = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="orders"),
            InlineKeyboardButton("◀ Back", callback_data="menu"),
        ]]
        if not self.get_orders_callback:
            return "📋 Orders callback not configured.", InlineKeyboardMarkup(keyboard)

        try:
            orders = await self.get_orders_callback()
            if not orders:
                return "📋 <b>Open Orders</b>\n\nNo open orders.", InlineKeyboardMarkup(keyboard)

            text = "<b>📋 Open Orders</b>\n\n"
            for i, order in enumerate(orders, 1):
                side = str(order.get('side', 'BUY')).upper()
                order_type = str(order.get('order_type', 'LIMIT')).upper()
                price = order.get('price') or 0
                text += f"<b>{i}. {order['symbol']} {side}</b>\n"
                text += f"   Type: {order_type}\n"
                text += f"   Size: {abs(order['size']):.4f}\n"
                text += f"   Price: ${price:,.2f}\n"
                if order.get('trigger_price'):
                    text += f"   Trigger: ${order['trigger_price']:,.2f}\n"
                text += "\n"
            return self._truncate(text.strip()), InlineKeyboardMarkup(keyboard)
        except Exception as e:
            return f"❌ Error: {e}", InlineKeyboardMarkup(keyboard)

    async def _build_pnl_view(self) -> tuple:
        keyboard = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="pnl"),
            InlineKeyboardButton("◀ Back", callback_data="menu"),
        ]]
        if not self.get_pnl_callback:
            return "💰 PnL callback not configured.", InlineKeyboardMarkup(keyboard)
        try:
            text = await self.get_pnl_callback()
            return self._truncate(text), InlineKeyboardMarkup(keyboard)
        except Exception as e:
            return f"❌ Error: {e}", InlineKeyboardMarkup(keyboard)

    async def _build_status_view(self) -> tuple:
        keyboard = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="status"),
            InlineKeyboardButton("◀ Back", callback_data="menu"),
        ]]
        if not self.get_status_callback:
            return "📊 Status callback not configured.", InlineKeyboardMarkup(keyboard)
        try:
            text = await self.get_status_callback()
            return self._truncate(text), InlineKeyboardMarkup(keyboard)
        except Exception as e:
            return f"❌ Error: {e}", InlineKeyboardMarkup(keyboard)

    async def _build_target_view(self) -> tuple:
        keyboard = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="target_refresh"),
            InlineKeyboardButton("◀ Back", callback_data="menu"),
        ]]
        if not self.get_target_state_callback:
            return "🎯 Target callback not configured.", InlineKeyboardMarkup(keyboard)
        try:
            data = await self.get_target_state_callback()
            addr = data['address']
            short_addr = f"{addr[:10]}...{addr[-6:]}" if len(addr) > 16 else addr
            pnl = data['unrealized_pnl']
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            text = (
                f"🎯 <b>Target Wallet</b>\n\n"
                f"<code>{short_addr}</code>\n\n"
                f"💼 Balance: ${data['balance']:,.2f}\n"
                f"📊 Equity: ${data['total_equity']:,.2f}\n"
                f"{pnl_emoji} Unrealized PnL: ${pnl:,.2f}\n"
                f"📍 Open Positions: {data['position_count']}\n"
                f"📝 Open Orders: {data['order_count']}\n"
                f"\n🕐 <i>Updated: {datetime.now().strftime('%H:%M:%S UTC')}</i>"
            )
            return text, InlineKeyboardMarkup(keyboard)
        except Exception as e:
            return f"❌ Error: {e}", InlineKeyboardMarkup(keyboard)

    async def _build_settings_menu(self) -> tuple:
        data = {}
        if self.get_settings_callback:
            data = self.get_settings_callback()

        lev = round(data.get('leverage_ratio', 1.0), 1)
        max_trades = data.get('max_trades', None)
        max_trades_str = str(max_trades) if max_trades is not None else "unlimited"
        blocked = data.get('blocked_assets', [])
        sim_mode = data.get('simulated_trading', True)

        text = (
            f"⚙️ <b>Settings</b>\n\n"
            f"<b>Leverage Ratio:</b> {lev}x of target\n"
            f"<b>Max Open Trades:</b> {max_trades_str}\n"
            f"<b>Mode:</b> {'🧪 Simulated' if sim_mode else '⚡ LIVE'}\n"
            f"<b>Blocked Assets:</b> {', '.join(blocked) if blocked else 'None'}\n"
        )

        # Per-blocked-asset remove buttons
        blocked_rows = [
            [InlineKeyboardButton(f"➖ Remove {asset}", callback_data=f"settings_blocked_remove:{asset}")]
            for asset in blocked
        ]

        mode_btn_label = "🔴 Switch to LIVE" if sim_mode else "🧪 Switch to Simulated"

        keyboard = [
            [
                InlineKeyboardButton("◀ Lev -0.1", callback_data="settings_lev_down"),
                InlineKeyboardButton(f"⚖️ {lev}x", callback_data="noop"),
                InlineKeyboardButton("Lev +0.1 ▶", callback_data="settings_lev_up"),
            ],
            [
                InlineKeyboardButton("◀ Trades -1", callback_data="settings_max_trades_down"),
                InlineKeyboardButton(f"🔢 {max_trades_str}", callback_data="noop"),
                InlineKeyboardButton("Trades +1 ▶", callback_data="settings_max_trades_up"),
            ],
            [InlineKeyboardButton("♾️ Set Unlimited", callback_data="settings_max_trades_unlimited")],
            *blocked_rows,
            [InlineKeyboardButton("➕ Add Blocked Asset", callback_data="settings_blocked_add")],
            [InlineKeyboardButton(mode_btn_label, callback_data="settings_toggle_sim")],
            [InlineKeyboardButton("◀ Back", callback_data="menu")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ─── Command handlers ────────────────────────────────────────────────────

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        text, markup = await self._build_main_menu()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        text, markup = await self._build_status_view()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def _positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        text, markup = await self._build_positions_menu()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def _orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        text, markup = await self._build_orders_view()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def _pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        text, markup = await self._build_pnl_view()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def _pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                await update.message.reply_text(f"❌ Error: {e}")

    async def _resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                await update.message.reply_text(f"❌ Error: {e}")

    async def _app_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        if not self.webapp_url:
            await update.message.reply_text(
                "⚠️ Web App URL not configured.\n\n"
                "Add <code>WEBAPP_URL=https://your-domain.com</code> to your <code>.env</code> file.",
                parse_mode="HTML"
            )
            return
        keyboard = [[
            InlineKeyboardButton("🚀 Open Dashboard", web_app=WebAppInfo(url=self.webapp_url))
        ]]
        await update.message.reply_text(
            "Tap the button below to open the trading dashboard:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ Unauthorized")
            return
        keyboard = [
            [
                InlineKeyboardButton("🔴 Close Positions", callback_data="stop_close"),
                InlineKeyboardButton("🟡 Keep Positions", callback_data="stop_keep"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="stop_cancel")],
        ]
        await update.message.reply_text(
            "⚠️ <b>STOP COPY TRADING</b>\n\n"
            "This will:\n"
            "✅ Stop copying new trades\n"
            "✅ Cancel all open orders\n\n"
            "Do you want to close all positions too?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    # ─── Button callback (central router) ────────────────────────────────────

    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not self._check_authorized(update):
            await query.edit_message_text("⛔ Unauthorized")
            return

        data = query.data

        # ── Navigation ──────────────────────────────────────────────────────
        if data == "menu":
            text, markup = await self._build_main_menu()
            await self._safe_edit(query, text, markup)

        elif data == "positions":
            text, markup = await self._build_positions_menu()
            await self._safe_edit(query, text, markup)

        elif data == "orders":
            text, markup = await self._build_orders_view()
            await self._safe_edit(query, text, markup)

        elif data == "pnl":
            text, markup = await self._build_pnl_view()
            await self._safe_edit(query, text, markup)

        elif data == "status":
            text, markup = await self._build_status_view()
            await self._safe_edit(query, text, markup)

        elif data in ("target", "target_refresh"):
            if data == "target_refresh" and self.refresh_target_callback:
                await self.refresh_target_callback()
            text, markup = await self._build_target_view()
            await self._safe_edit(query, text, markup)

        elif data == "settings":
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        # ── Bot control ─────────────────────────────────────────────────────
        elif data == "pause":
            if self.on_pause_requested:
                await self.on_pause_requested()
            keyboard = [[InlineKeyboardButton("◀ Back to Menu", callback_data="menu")]]
            await self._safe_edit(
                query,
                "⏸️ <b>Bot Paused</b>\n\nNo new trades will be copied.\nExisting positions remain open.",
                InlineKeyboardMarkup(keyboard)
            )

        elif data == "resume":
            if self.on_resume_requested:
                await self.on_resume_requested()
            keyboard = [[InlineKeyboardButton("◀ Back to Menu", callback_data="menu")]]
            await self._safe_edit(
                query,
                "▶️ <b>Bot Resumed</b>\n\nCopying trades is now active!",
                InlineKeyboardMarkup(keyboard)
            )

        # ── Position close ──────────────────────────────────────────────────
        elif data.startswith("pos_close:"):
            symbol = data.split(":", 1)[1]
            await query.edit_message_text(f"⏳ Closing {symbol} position...", parse_mode="HTML")
            success = False
            if self.close_position_callback:
                success = await self.close_position_callback(symbol)
            result_text = f"✅ {symbol} position close requested." if success else f"❌ Failed to close {symbol}."
            keyboard = [
                [InlineKeyboardButton("📍 Back to Positions", callback_data="positions")],
                [InlineKeyboardButton("◀ Main Menu", callback_data="menu")],
            ]
            await query.edit_message_text(result_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

        # ── Settings: leverage ──────────────────────────────────────────────
        elif data == "settings_lev_up":
            if self.update_setting_callback and self.get_settings_callback:
                current = round(self.get_settings_callback().get('leverage_ratio', 1.0), 1)
                await self.update_setting_callback("leverage_ratio", current + 0.1)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        elif data == "settings_lev_down":
            if self.update_setting_callback and self.get_settings_callback:
                current = round(self.get_settings_callback().get('leverage_ratio', 1.0), 1)
                await self.update_setting_callback("leverage_ratio", current - 0.1)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        # ── Settings: max trades ────────────────────────────────────────────
        elif data == "settings_max_trades_up":
            if self.update_setting_callback and self.get_settings_callback:
                current = self.get_settings_callback().get('max_trades', None)
                new_val = (current or 0) + 1
                await self.update_setting_callback("max_trades", new_val)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        elif data == "settings_max_trades_down":
            if self.update_setting_callback and self.get_settings_callback:
                current = self.get_settings_callback().get('max_trades', None)
                if current is not None and current > 1:
                    await self.update_setting_callback("max_trades", current - 1)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        elif data == "settings_max_trades_unlimited":
            if self.update_setting_callback:
                await self.update_setting_callback("max_trades", None)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        # ── Settings: blocked assets ────────────────────────────────────────
        elif data.startswith("settings_blocked_remove:"):
            asset = data.split(":", 1)[1]
            if self.update_setting_callback:
                await self.update_setting_callback("blocked_remove", asset)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        elif data == "settings_blocked_add":
            chat_id = str(update.effective_chat.id)
            self._awaiting_input[chat_id] = {"action": "blocked_add"}
            keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="settings_blocked_add_cancel")]]
            await self._safe_edit(
                query,
                "➕ <b>Add Blocked Asset</b>\n\nType the asset symbol to block (e.g. <code>BTC</code>):",
                InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings_blocked_add_cancel":
            chat_id = str(update.effective_chat.id)
            self._awaiting_input.pop(chat_id, None)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        # ── Settings: sim/live toggle ───────────────────────────────────────
        elif data == "settings_toggle_sim":
            sim_mode = True
            if self.get_settings_callback:
                sim_mode = self.get_settings_callback().get('simulated_trading', True)
            new_mode_str = "LIVE ⚡" if sim_mode else "Simulated 🧪"
            warning = "⚠️ <b>WARNING: Switching to LIVE mode will use real funds!</b>\n\n" if sim_mode else ""
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data="settings_toggle_sim_confirm"),
                    InlineKeyboardButton("❌ Cancel", callback_data="settings"),
                ]
            ]
            await self._safe_edit(
                query,
                f"{warning}Switch trading mode to <b>{new_mode_str}</b>?\n\nThis takes effect immediately.",
                InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings_toggle_sim_confirm":
            if self.update_setting_callback:
                await self.update_setting_callback("sim_mode", None)
            text, markup = await self._build_settings_menu()
            await self._safe_edit(query, text, markup)

        # ── Stop flow (preserved) ───────────────────────────────────────────
        elif data == "stop_close":
            await query.edit_message_text(
                "🛑 <b>Stopping bot...</b>\n\n• Cancelling all orders\n• Closing all positions\n• Shutting down\n\nPlease wait...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=True)
                    await query.edit_message_text(
                        "✅ <b>Bot Stopped</b>\n\nAll orders cancelled.\nAll positions closed.\nStatus: 🔴 INACTIVE",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Error: {e}")

        elif data == "stop_keep":
            await query.edit_message_text(
                "🛑 <b>Stopping bot...</b>\n\n• Cancelling all orders\n• Keeping positions open\n• Shutting down\n\nPlease wait...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=False)
                    await query.edit_message_text(
                        "✅ <b>Bot Stopped</b>\n\nAll orders cancelled.\nPositions kept open.\nStatus: 🔴 INACTIVE",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Error: {e}")

        elif data == "stop_cancel":
            await self._safe_edit(query, "✅ Stop cancelled. Bot is still running.")

        # ── No-op (decorative display buttons) ─────────────────────────────
        elif data == "noop":
            pass  # query.answer() already called; nothing to do

        else:
            logger.warning(f"Unknown callback_data: {data}")

    # ─── Text message handler (for settings input flows) ─────────────────────

    async def _text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_authorized(update):
            return
        chat_id = str(update.effective_chat.id)
        pending = self._awaiting_input.get(chat_id)
        if not pending:
            return

        action = pending.get("action")
        user_text = update.message.text.strip().upper()

        if action == "blocked_add":
            self._awaiting_input.pop(chat_id, None)
            if self.update_setting_callback:
                ok, msg = await self.update_setting_callback("blocked_add", user_text)
                result = f"{'✅' if ok else '❌'} {msg}\n\n"
            else:
                result = "❌ Settings callback not configured.\n\n"
            text, markup = await self._build_settings_menu()
            await update.message.reply_text(result + text, reply_markup=markup, parse_mode="HTML")

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        logger.info("Starting Telegram bot...")
        self.app = Application.builder().token(self.bot_token).build()

        # Command handlers
        self.app.add_handler(CommandHandler("start", self._start_command))
        self.app.add_handler(CommandHandler("menu", self._start_command))
        self.app.add_handler(CommandHandler("app", self._app_command))
        self.app.add_handler(CommandHandler("status", self._status_command))
        self.app.add_handler(CommandHandler("positions", self._positions_command))
        self.app.add_handler(CommandHandler("orders", self._orders_command))
        self.app.add_handler(CommandHandler("pnl", self._pnl_command))
        self.app.add_handler(CommandHandler("pause", self._pause_command))
        self.app.add_handler(CommandHandler("resume", self._resume_command))
        self.app.add_handler(CommandHandler("stop", self._stop_command))

        # Inline keyboard callback router
        self.app.add_handler(CallbackQueryHandler(self._button_callback))

        # Text input handler for settings flows
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._text_message_handler)
        )

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        logger.info("✅ Telegram bot started and polling")

    async def stop(self):
        if self.app:
            logger.info("Stopping Telegram bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")
