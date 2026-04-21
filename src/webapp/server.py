import hashlib
import hmac
import json
from typing import Optional, Callable
from urllib.parse import parse_qs, unquote
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger


def _validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram WebApp initData signature and return parsed fields."""
    parsed = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            parsed[k] = unquote(v)

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("No hash in initData")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid signature")

    return parsed


class WebAppServer:
    """
    FastAPI web server that exposes the bot state as a REST API
    consumed by the Telegram Mini App frontend.
    """

    def __init__(self, port: int = 8080, bot_token: str = "", allowed_user_id: str = ""):
        self.port = port
        self.bot_token = bot_token
        self.allowed_user_id = str(allowed_user_id)

        # Callbacks — same pattern as TelegramBot
        self.get_status_callback: Optional[Callable] = None
        self.get_positions_callback: Optional[Callable] = None   # returns list[dict]
        self.get_orders_callback: Optional[Callable] = None      # returns list[dict]
        self.get_pnl_callback: Optional[Callable] = None         # returns str
        self.get_target_state_callback: Optional[Callable] = None
        self.close_position_callback: Optional[Callable] = None
        self.update_setting_callback: Optional[Callable] = None
        self.get_settings_callback: Optional[Callable] = None    # sync lambda
        self.get_pause_state_callback: Optional[Callable] = None # sync lambda
        self.on_pause_requested: Optional[Callable] = None
        self.on_resume_requested: Optional[Callable] = None

        self.app = FastAPI(title="Hyperliquid Dashboard", docs_url=None, redoc_url=None)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._setup_routes()

        static_dir = Path(__file__).parent / "static"
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ─── Auth ────────────────────────────────────────────────────────────────

    def _authorize(self, init_data: Optional[str]) -> None:
        """Raise HTTPException 401 if the request is not from the authorized user."""
        if not init_data:
            raise HTTPException(status_code=401, detail="Missing auth header")
        if not self.bot_token:
            raise HTTPException(status_code=401, detail="Bot token not configured")
        try:
            parsed = _validate_telegram_init_data(init_data, self.bot_token)
            user_json = parsed.get("user", "{}")
            user = json.loads(user_json)
            if str(user.get("id", "")) != self.allowed_user_id:
                raise ValueError("User not authorized")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"WebApp auth rejected: {e}")
            raise HTTPException(status_code=401, detail="Unauthorized")

    # ─── Serialization helpers ────────────────────────────────────────────────

    @staticmethod
    def _serialize(obj):
        """Convert enum/dataclass values to JSON-safe types."""
        if hasattr(obj, "value"):
            return obj.value
        return obj

    def _clean_dict(self, d: dict) -> dict:
        return {k: self._serialize(v) for k, v in d.items()}

    # ─── Routes ──────────────────────────────────────────────────────────────

    def _setup_routes(self):
        app = self.app

        @app.get("/")
        async def index():
            return FileResponse(str(Path(__file__).parent / "static" / "index.html"))

        # ── Read endpoints ────────────────────────────────────────────────────

        @app.get("/api/status")
        async def api_status(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            paused = self.get_pause_state_callback() if self.get_pause_state_callback else False
            data = {"paused": paused}
            if self.get_settings_callback:
                cfg = self.get_settings_callback()
                data["simulated"] = cfg.get("simulated_trading", True)
            if self.get_status_callback:
                data["text"] = await self.get_status_callback()
            return data

        @app.get("/api/positions")
        async def api_positions(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.get_positions_callback:
                raw = await self.get_positions_callback()
                return {"positions": [self._clean_dict(p) for p in raw]}
            return {"positions": []}

        @app.get("/api/orders")
        async def api_orders(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.get_orders_callback:
                raw = await self.get_orders_callback()
                return {"orders": [self._clean_dict(o) for o in raw]}
            return {"orders": []}

        @app.get("/api/pnl")
        async def api_pnl(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.get_pnl_callback:
                text = await self.get_pnl_callback()
                return {"text": text}
            return {"text": ""}

        @app.get("/api/target")
        async def api_target(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.get_target_state_callback:
                return await self.get_target_state_callback()
            return {}

        @app.get("/api/settings")
        async def api_settings(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.get_settings_callback:
                return self.get_settings_callback()
            return {}

        # ── Write endpoints ───────────────────────────────────────────────────

        @app.post("/api/pause")
        async def api_pause(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.on_pause_requested:
                await self.on_pause_requested()
            return {"ok": True}

        @app.post("/api/resume")
        async def api_resume(x_telegram_init_data: Optional[str] = Header(None)):
            self._authorize(x_telegram_init_data)
            if self.on_resume_requested:
                await self.on_resume_requested()
            return {"ok": True}

        @app.post("/api/positions/{symbol}/close")
        async def api_close_position(
            symbol: str,
            x_telegram_init_data: Optional[str] = Header(None),
        ):
            self._authorize(x_telegram_init_data)
            if self.close_position_callback:
                ok = await self.close_position_callback(symbol)
                return {"ok": ok}
            return {"ok": False}

        @app.post("/api/settings")
        async def api_update_setting(
            request: Request,
            x_telegram_init_data: Optional[str] = Header(None),
        ):
            self._authorize(x_telegram_init_data)
            body = await request.json()
            if self.update_setting_callback:
                ok, msg = await self.update_setting_callback(body.get("key"), body.get("value"))
                return {"ok": ok, "message": msg}
            return {"ok": False, "message": "Not configured"}

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        logger.info(f"Starting WebApp server on port {self.port}...")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            loop="none",
            log_level="warning",
        )
        server = uvicorn.Server(config)
        await server.serve()
