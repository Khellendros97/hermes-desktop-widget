"""WebSocket platform adapter for Hermes Desktop Panel.

Runs a WebSocket server that desktop clients connect to for bidirectional
real-time communication with the Hermes agent. Follows the standard
BasePlatformAdapter interface.

Security requires a token configured in ~/.hermes/config.yaml:
  platforms.desktop.token: "your-secret-here"

Usage:
  Add to ~/.hermes/config.yaml and run `hermes gateway start`.
"""

import asyncio
import json
import logging
import ssl
import time
from typing import Any, Dict, Optional, Set

try:
    from aiohttp import web, WSMsgType, WSCloseCode
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None
    WSMsgType = None
    WSCloseCode = None

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8643


def check_desktop_requirements() -> bool:
    return AIOHTTP_AVAILABLE


class DesktopAdapter(BasePlatformAdapter):
    """WebSocket adapter for Hermes Desktop Panel clients."""

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.DESKTOP)
        extra = config.extra or {}
        self._host: str = extra.get("host", DEFAULT_HOST)
        self._port: int = int(extra.get("port", DEFAULT_PORT))
        self._token: str = config.token or extra.get("token", "")
        self._tls_cert: str = extra.get("tls_cert", "")
        self._tls_key: str = extra.get("tls_key", "")

        self._connections: Dict[str, web.WebSocketResponse] = {}
        self._background_tasks: Set[asyncio.Task] = set()

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    # ── Lifecycle ──

    async def connect(self) -> bool:
        if not self._token:
            raise ValueError(
                "[desktop] Token is required. Set platforms.desktop.token in config.yaml."
            )

        self._app = web.Application()
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_get("/health", self._handle_health)

        ssl_context = None
        if self._tls_cert and self._tls_key:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(self._tls_cert, self._tls_key)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port, ssl_context=ssl_context)
        await site.start()

        protocol = "wss" if ssl_context else "ws"
        self._mark_connected()
        logger.info(
            "[desktop] Listening on %s://%s:%d/ws",
            protocol, self._host, self._port,
        )
        return True

    async def disconnect(self) -> None:
        for ws in list(self._connections.values()):
            try:
                await ws.close(code=WSCloseCode.GOING_AWAY, message=b"Server shutting down")
            except Exception:
                pass
        self._connections.clear()

        for task in list(self._background_tasks):
            task.cancel()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._mark_disconnected()
        logger.info("[desktop] Disconnected")

    # ── Send ──

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        ws = self._connections.get(chat_id)
        if ws is None or ws.closed:
            return SendResult(success=False, error="Client not connected")

        try:
            meta = metadata or {}
            if meta.get("delta"):
                payload = {"type": "delta", "text": content, "seq": meta.get("seq", 0)}
            elif meta.get("type") == "notification":
                payload = {"type": "notification", "text": content, "level": meta.get("level", "info")}
            elif meta.get("type") == "done":
                payload = {"type": "done", "session_id": meta.get("session_id", "")}
            else:
                payload = {"type": "delta", "text": content, "seq": 0}

            await ws.send_json(payload)
            return SendResult(success=True)
        except Exception as e:
            logger.error("[desktop] send error: %s", e)
            return SendResult(success=False, error=str(e))

    # ── HTTP Handlers ──

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "platform": "desktop"})

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        authenticated = False
        chat_id = ""

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    authenticated, chat_id = await self._process_message(
                        ws, msg.data, authenticated, chat_id
                    )
                elif msg.type == WSMsgType.ERROR:
                    logger.error("[desktop] ws error: %s", ws.exception())
        finally:
            if chat_id:
                self._connections.pop(chat_id, None)

        return ws

    async def _process_message(
        self, ws: web.WebSocketResponse, raw: str,
        authenticated: bool, chat_id: str,
    ) -> tuple[bool, str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "text": "Invalid JSON"})
            return authenticated, chat_id

        msg_type = data.get("type", "")

        if msg_type == "auth":
            token = data.get("token", "")
            if not token or token != self._token:
                await ws.send_json({"type": "error", "text": "Auth failed: invalid token"})
                await ws.close(code=WSCloseCode.POLICY_VIOLATION, message=b"Invalid token")
                return False, ""
            self._connections[token] = ws
            await ws.send_json({"type": "auth_ok"})
            return True, token

        if not authenticated:
            await ws.send_json({"type": "error", "text": "Authenticate first"})
            return False, ""

        if msg_type == "ping":
            await ws.send_json({"type": "pong"})
            return True, chat_id

        if msg_type == "message":
            text = data.get("text", "").strip()
            if not text:
                return True, chat_id

            source = self.build_source(
                chat_id=chat_id,
                chat_name="Desktop Panel",
                chat_type="desktop",
                user_id=chat_id,
                user_name="User",
            )
            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                source=source,
                raw_message=data,
            )

            task = asyncio.create_task(self.handle_message(event))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return True, chat_id

        return True, chat_id

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return info about a connected desktop session."""
        return {
            "name": "Desktop Panel",
            "type": "desktop",
            "session": chat_id,
        }
