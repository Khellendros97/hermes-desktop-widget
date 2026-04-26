# Hermes 桌面灵动岛组件 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 开发一个"灵动岛"风格桌面小组件，通过 WebSocket 连接远程 Hermes Agent 网关，实现消息收发、流式展示、系统托盘、消息历史等完整体验。

**Architecture:** 服务端新增 `gateway/platforms/desktop.py` WebSocket 适配器（一个标准 Hermes 平台适配器，处理认证、消息路由、流式推送）。客户端用 PyQt6 构建独立桌面应用，通过 WSS（TLS）连接服务端，采用状态机管理面板的隐藏/通知/交互三种状态。

**Tech Stack:** Python 3.10+, PyQt6, aiohttp (服务端), websocket-client (客户端), SQLite (本地存储)

---

## 项目结构

```
hermes-panel/                        # 桌面组件项目
├── main.py                          # 入口
├── requirements.txt
├── docs/plans/                      # 本文件
├── hermes_panel/
│   ├── __init__.py
│   ├── config.py                    # 配置管理（QSettings）
│   ├── client.py                    # WebSocket 客户端 + 重连 + 心跳
│   ├── protocol.py                  # 消息协议数据类
│   ├── store.py                     # SQLite 消息存储
│   ├── panel.py                     # 灵动岛面板核心 UI
│   ├── tray.py                      # 系统托盘
│   ├── settings_dialog.py           # 设置对话框
│   └── resources/
│       ├── icon.png                 # 托盘图标
│       ├── icon.ico                 # 窗口图标
│       └── styles.qss              # 全局样式表
├── tests/
│   ├── __init__.py
│   ├── test_protocol.py
│   ├── test_store.py
│   └── test_client.py
└── scripts/
    └── build_exe.py                 # PyInstaller 打包脚本
```

Hermes 服务端新增文件（放到 hermes-agent 仓库中）：
```
gateway/platforms/desktop.py          # WebSocket 适配器
```

---

### Task 1: 项目骨架搭建

**文件：**
- 创建：`requirements.txt`
- 创建：`hermes_panel/__init__.py`
- 创建：`hermes_panel/config.py`

**Step 1: 编写 requirements.txt**

```
PyQt6>=6.6.0
websocket-client>=1.7.0
```

**Step 2: 编写 hermes_panel/__init__.py**

```python
"""Hermes Desktop Panel - 灵动岛桌面小组件."""
__version__ = "0.1.0"
```

**Step 3: 编写 config.py**

```python
"""使用 QSettings 持久化配置，供所有模块读取。"""
from PyQt6.QtCore import QSettings

SETTINGS = QSettings("HermesPanel", "config")

DEFAULTS = {
    "server/host": "127.0.0.1",
    "server/port": 8643,
    "server/token": "",
    "server/tls": True,
    "server/verify_cert": True,
    "panel/x": -1,              # -1 表示未设置，首次启动居中
    "panel/hide_delay_ms": 5000,
    "app/autostart": False,
}

def get(key: str) -> str:
    return SETTINGS.value(key, DEFAULTS.get(key, ""))

def set_(key: str, value):
    SETTINGS.setValue(key, value)
```

**Step 4: 提交**

---

### Task 2: 消息协议定义

**文件：**
- 创建：`hermes_panel/protocol.py`
- 创建：`tests/test_protocol.py`

**Step 1: 编写测试**

```python
"""tests/test_protocol.py"""
import json
import pytest
from hermes_panel.protocol import (
    OutgoingMessage, IncomingDelta, IncomingDone,
    IncomingNotification, IncomingError, IncomingAuthOk,
    deserialize,
)

def test_outgoing_message_serialize():
    msg = OutgoingMessage(text="你好")
    data = msg.to_dict()
    assert data == {"type": "message", "text": "你好"}

def test_outgoing_auth_serialize():
    msg = OutgoingMessage(type_="auth", token="secret")
    data = msg.to_dict()
    assert data == {"type": "auth", "token": "secret"}

def test_outgoing_ping_serialize():
    msg = OutgoingMessage(type_="ping")
    data = msg.to_dict()
    assert data == {"type": "ping"}

def test_deserialize_delta():
    raw = json.dumps({"type": "delta", "text": "你好世界", "seq": 3})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingDelta)
    assert msg.text == "你好世界"
    assert msg.seq == 3

def test_deserialize_done():
    raw = json.dumps({"type": "done", "session_id": "abc123"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingDone)
    assert msg.session_id == "abc123"

def test_deserialize_notification():
    raw = json.dumps({"type": "notification", "text": "后台任务完成", "level": "info"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingNotification)
    assert msg.text == "后台任务完成"
    assert msg.level == "info"

def test_deserialize_error():
    raw = json.dumps({"type": "error", "text": "认证失败"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingError)
    assert msg.text == "认证失败"

def test_deserialize_unknown():
    raw = json.dumps({"type": "unknown", "data": 42})
    msg = deserialize(raw)
    assert msg is None
```


**Step 2: 运行测试确认失败**

```bash
pytest tests/test_protocol.py -v
```
预期：全部 FAIL（模块不存在）

**Step 3: 编写实现**

```python
"""hermes_panel/protocol.py - 与 Hermes desktop 适配器的 WebSocket 消息协议。"""
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class OutgoingMessage:
    """客户端 → 服务端。"""
    type_: str = "message"
    text: str = ""
    token: str = ""

    def to_dict(self) -> dict:
        d = {"type": self.type_}
        if self.text:
            d["text"] = self.text
        if self.token:
            d["token"] = self.token
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class IncomingDelta:
    """服务端 → 客户端：流式回复片段。"""
    text: str
    seq: int = 0


@dataclass
class IncomingDone:
    """服务端 → 客户端：本轮对话完成。"""
    session_id: str = ""


@dataclass
class IncomingNotification:
    """服务端 → 客户端：系统通知（后台任务完成等）。"""
    text: str
    level: str = "info"  # info / warning / error


@dataclass
class IncomingError:
    """服务端 → 客户端：错误。"""
    text: str


@dataclass
class IncomingAuthOk:
    """服务端 → 客户端：认证成功。"""
    pass


_TYPE_MAP = {
    "delta": IncomingDelta,
    "done": IncomingDone,
    "notification": IncomingNotification,
    "error": IncomingError,
    "auth_ok": IncomingAuthOk,
}


def deserialize(raw: str):
    """从 JSON 字符串解析为对应的消息对象。未知类型返回 None。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    msg_type = data.get("type", "")
    cls = _TYPE_MAP.get(msg_type)
    if cls is None:
        return None

    if cls is IncomingDelta:
        return cls(text=data.get("text", ""), seq=data.get("seq", 0))
    elif cls is IncomingDone:
        return cls(session_id=data.get("session_id", ""))
    elif cls is IncomingNotification:
        return cls(text=data.get("text", ""), level=data.get("level", "info"))
    elif cls is IncomingError:
        return cls(text=data.get("text", ""))
    elif cls is IncomingAuthOk:
        return cls()
    return None
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/test_protocol.py -v
```

**Step 5: 提交**

```bash
git add tests/test_protocol.py hermes_panel/protocol.py
git commit -m "feat: define WebSocket message protocol with serialization tests"
```

---

### Task 3: SQLite 消息存储

**文件：**
- 创建：`hermes_panel/store.py`
- 创建：`tests/test_store.py`

**Step 1: 编写测试**

```python
"""tests/test_store.py"""
import tempfile
import os
import pytest
from hermes_panel.store import MessageStore


@pytest.fixture
def store():
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    s = MessageStore(db_path)
    yield s
    s.close()


def test_save_and_get_messages(store):
    store.save_message("user", "你好")
    store.save_message("assistant", "你好！有什么可以帮你？")

    messages = store.get_messages(limit=10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "你好"
    assert messages[1]["role"] == "assistant"


def test_get_messages_with_limit(store):
    for i in range(5):
        store.save_message("user", f"msg {i}")

    messages = store.get_messages(limit=3)
    assert len(messages) == 3


def test_get_messages_by_session(store):
    store.save_message("user", "msg1", session_id="s1")
    store.save_message("assistant", "msg2", session_id="s1")
    store.save_message("user", "msg3", session_id="s2")

    s1 = store.get_messages(session_id="s1")
    assert len(s1) == 2

    s2 = store.get_messages(session_id="s2")
    assert len(s2) == 1


def test_clear_messages(store):
    store.save_message("user", "msg")
    store.clear_messages()
    assert len(store.get_messages()) == 0
```

**Step 2: 运行测试确认失败** → `pytest tests/test_store.py -v`

**Step 3: 编写实现**

```python
"""hermes_panel/store.py - SQLite 消息存储。"""
import sqlite3
import os
from typing import Optional


class MessageStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT DEFAULT '',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._conn.commit()

    def save_message(self, role: str, content: str, session_id: str = ""):
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        self._conn.commit()

    def get_messages(
        self,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]

    def clear_messages(self):
        self._conn.execute("DELETE FROM messages")
        self._conn.commit()

    def close(self):
        self._conn.close()
```

**Step 4: 运行测试确认通过** → `pytest tests/test_store.py -v`

**Step 5: 提交**

---

### Task 4: WebSocket 客户端

**文件：**
- 创建：`hermes_panel/client.py`

**说明：** 使用 `websocket-client` 库实现 WebSocket 客户端，包含自动重连（指数退避 1s→30s）、心跳（每 30s ping）、TLS 支持。通过 Qt 信号将服务端消息分发给 UI 层。

```python
"""hermes_panel/client.py - WebSocket 客户端，管理与 Hermes 服务器的连接。"""
import json
import time
import threading
from typing import Optional

import websocket
from PyQt6.QtCore import QObject, pyqtSignal

from hermes_panel.protocol import (
    OutgoingMessage, deserialize,
    IncomingDelta, IncomingDone, IncomingNotification,
    IncomingError, IncomingAuthOk,
)


class HermesClient(QObject):
    """Hermes WebSocket 客户端。

    管理 WebSocket 连接生命周期（连接、认证、心跳、重连），
    通过 Qt 信号将服务端消息传递给 UI 层。
    """

    # 信号
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    auth_ok = pyqtSignal()
    delta_received = pyqtSignal(str, int)        # text, seq
    done_received = pyqtSignal(str)              # session_id
    notification_received = pyqtSignal(str, str) # text, level
    error_occurred = pyqtSignal(str)             # error text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._should_stop = False
        self._reconnect_delay = 1  # 秒，指数退避起始值
        self._url = ""
        self._token = ""
        self._verify_cert = True

    def connect_to_server(self, host: str, port: int, token: str, tls: bool = True, verify_cert: bool = True):
        """连接到 Hermes 服务器。如果已连接则先断开。"""
        self._should_stop = False
        self._url = f"{'wss' if tls else 'ws'}://{host}:{port}"
        self._token = token
        self._verify_cert = verify_cert
        self._reconnect_delay = 1
        self._start()

    def disconnect(self):
        """断开连接并停止重连。"""
        self._should_stop = True
        if self._ws:
            self._ws.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def send_message(self, text: str):
        """发送用户消息到 Hermes。"""
        if self._ws:
            msg = OutgoingMessage(text=text)
            self._ws.send(msg.to_json())

    # ── 内部实现 ──

    def _start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._should_stop:
            self._ws = websocket.WebSocketApp(
                self._url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            ssl_opt = None
            if self._url.startswith("wss://"):
                ssl_opt = {"cert_reqs": 0} if not self._verify_cert else {}
            self._ws.run_forever(
                ping_interval=30,
                ping_timeout=10,
                sslopt=ssl_opt,
            )

            if self._should_stop:
                break

            # 指数退避重连
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 30)

    def _on_open(self, ws):
        self._reconnect_delay = 1
        # 发送认证
        auth_msg = OutgoingMessage(type_="auth", token=self._token)
        ws.send(auth_msg.to_json())
        self.connected.emit()

    def _on_message(self, ws, raw: str):
        msg = deserialize(raw)
        if msg is None:
            return

        if isinstance(msg, IncomingAuthOk):
            self.auth_ok.emit()
        elif isinstance(msg, IncomingDelta):
            self.delta_received.emit(msg.text, msg.seq)
        elif isinstance(msg, IncomingDone):
            self.done_received.emit(msg.session_id)
        elif isinstance(msg, IncomingNotification):
            self.notification_received.emit(msg.text, msg.level)
        elif isinstance(msg, IncomingError):
            self.error_occurred.emit(msg.text)

    def _on_error(self, ws, error):
        # websocket-client 库在连接失败时会打印错误但不一定是致命错误
        pass

    def _on_close(self, ws, close_status_code, close_msg):
        self.disconnected.emit()
```

---

### Task 5: 服务端适配器（Hermes 仓库中）

**文件：**
- 创建（Hermes 仓库）：`gateway/platforms/desktop.py`

**说明：** 这是 Hermes 网关的平台适配器，遵循 BasePlatformAdapter 接口。在 `connect()` 中启动 aiohttp WebSocket 服务，处理客户端认证、消息转发、流式响应推送。

**Step 1: 编写适配器完整代码**

```python
"""WebSocket platform adapter for Hermes Desktop Panel.

Runs a WebSocket server that desktop clients connect to for
bidirectional real-time communication with the Hermes agent.

Security:
  - Token-based authentication required for all connections.
  - Supports TLS via configuration.
  - One WebSocket connection per token.
"""

import asyncio
import json
import logging
import ssl
import time
import uuid
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
        self._token: str = extra.get("token", "")
        self._tls_cert: str = extra.get("tls_cert", "")
        self._tls_key: str = extra.get("tls_key", "")

        # 活跃的 WebSocket 连接（每个 token 一个连接）
        self._connections: Dict[str, web.WebSocketResponse] = {}
        # 每个连接的当前 session_id（用于历史关联）
        self._session_ids: Dict[str, str] = {}
        # 后台任务 tracker
        self._background_tasks: set[asyncio.Task] = set()

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    # ── 生命周期 ──

    async def connect(self) -> bool:
        if not self._token:
            raise ValueError(
                "[desktop] token is required. Set platforms.desktop.token in config.yaml."
            )

        self._app = web.Application()
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_get("/health", self._handle_health)

        # TLS 配置
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
        # 关闭所有客户端连接
        for ws in list(self._connections.values()):
            try:
                await ws.close(code=WSCloseCode.GOING_AWAY, message=b"Server shutting down")
            except Exception:
                pass
        self._connections.clear()

        # 取消后台任务
        for task in list(self._background_tasks):
            task.cancel()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._mark_disconnected()
        logger.info("[desktop] Disconnected")

    # ── 消息发送 ──

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送消息到桌面客户端。

        chat_id 格式: ``desktop:{token}``
        metadata["delta"] = True 时发送流式增量
        metadata["type"] = "notification" 时发送通知
        """
        ws = self._connections.get(chat_id)
        if ws is None or ws.closed:
            return SendResult(success=False, error="Client not connected")

        try:
            meta = metadata or {}
            if meta.get("delta"):
                payload = {
                    "type": "delta",
                    "text": content,
                    "seq": meta.get("seq", 0),
                }
            elif meta.get("type") == "notification":
                payload = {
                    "type": "notification",
                    "text": content,
                    "level": meta.get("level", "info"),
                }
            elif meta.get("type") == "done":
                payload = {
                    "type": "done",
                    "session_id": meta.get("session_id", ""),
                }
            else:
                payload = {"type": "delta", "text": content, "seq": 0}

            await ws.send_json(payload)
            return SendResult(success=True)
        except Exception as e:
            logger.error("[desktop] send error: %s", e)
            return SendResult(success=False, error=str(e))

    # ── HTTP handlers ──

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
                    authenticated, chat_id = await self._process_message(ws, msg.data, authenticated, chat_id)
                elif msg.type == WSMsgType.ERROR:
                    logger.error("[desktop] ws error: %s", ws.exception())
        finally:
            if chat_id:
                self._connections.pop(chat_id, None)
                self._session_ids.pop(chat_id, None)

        return ws

    async def _process_message(
        self,
        ws: web.WebSocketResponse,
        raw: str,
        authenticated: bool,
        chat_id: str,
    ) -> tuple[bool, str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "text": "Invalid JSON"})
            return authenticated, chat_id

        msg_type = data.get("type", "")

        # ── 认证 ──
        if msg_type == "auth":
            token = data.get("token", "")
            if not token or token != self._token:
                await ws.send_json({"type": "error", "text": "认证失败：无效的 token"})
                await ws.close(code=WSCloseCode.POLICY_VIOLATION, message=b"Invalid token")
                return False, ""
            self._connections[token] = ws
            await ws.send_json({"type": "auth_ok"})
            return True, token

        if not authenticated:
            await ws.send_json({"type": "error", "text": "请先认证"})
            return False, ""

        # ── 心跳 ──
        if msg_type == "ping":
            await ws.send_json({"type": "pong"})
            return True, chat_id

        # ── 用户消息 ──
        if msg_type == "message":
            text = data.get("text", "").strip()
            if not text:
                return True, chat_id

            source = self.build_source(
                chat_id=chat_id,
                chat_name="桌面小组件",
                chat_type="desktop",
                user_id=chat_id,
                user_name="用户",
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
```

**Step 2: 注册 DESKTOP 平台枚举**

在 Hermes 仓库 `gateway/config.py` 的 `Platform` 枚举中添加：

```python
DESKTOP = "desktop"
```

**Step 3: 注册适配器**

在 `gateway/platforms/__init__.py` 或网关加载逻辑中注册：

```python
from gateway.platforms.desktop import DesktopAdapter, check_desktop_requirements
```

**Step 4: 配置示例（`~/.hermes/config.yaml`）**

```yaml
platforms:
  desktop:
    enabled: true
    token: "your-64-char-random-token"
    tls_cert: "/etc/ssl/certs/hermes.pem"
    tls_key: "/etc/ssl/private/hermes.key"
    host: "0.0.0.0"
    port: 8643
```

---

### Task 6: 灵动岛面板 UI（核心）

**文件：**
- 创建：`hermes_panel/panel.py`

**说明：** 这是整个组件最核心的 UI 文件。管理三种状态的切换和动画。

**三种状态：**
- **隐藏态**：顶部 4px 高度窄条，半透明灰色，完全不干扰操作
- **通知态**：收到消息时展开为 280×56 圆角矩形，显示消息摘要（首行文字）
- **交互态**：点击面板后展开为 380×480 区域，上方显示消息历史，下方输入框+发送按钮

**关键实现细节：**
- `Qt.WindowStaysOnTopHint` + `Qt.FramelessWindowHint` + `Qt.Tool`
- `QGraphicsOpacityEffect` 淡入淡出动画（200ms）
- `QPropertyAnimation` 展开/收起动画（geometry 变化，150ms ease-out）
- `mousePressEvent` / `mouseMoveEvent` 实现拖拽（限制 Y 坐标 0-50）
- `QSettings` 持久化位置
- `enterEvent` / `leaveEvent` 控制悬停行为
- `QTimer` 自动隐藏倒计时

```python
"""hermes_panel/panel.py - 灵动岛面板核心 UI。"""
import time
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint,
    QRect, pyqtSignal, QSettings,
)
from PyQt6.QtGui import (
    QFont, QPalette, QColor, QPainter, QBrush, QPen,
    QFontDatabase, QAction, QIcon,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QGraphicsOpacityEffect,
    QApplication,
)

from hermes_panel.config import SETTINGS, DEFAULTS, get, set_


class State:
    HIDDEN = "hidden"
    NOTIFY = "notify"
    INTERACTIVE = "interactive"


class MessageBubble(QWidget):
    """单条消息气泡。"""

    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self._role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._label = QLabel(content)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            "color: #e0e0e0; font-size: 13px;" if role == "assistant"
            else "color: #888; font-size: 12px;"
        )
        layout.addWidget(self._label)

    def append_text(self, text: str):
        """流式追加文字。"""
        self._label.setText(self._label.text() + text)

    def role(self) -> str:
        return self._role


class HermesPanel(QWidget):
    """灵动岛桌面面板。

    吸附屏幕顶部，平时隐藏为细条，收到消息展开，
    点击进入交互模式显示历史和输入框。
    """

    message_sent = pyqtSignal(str)  # 用户发送消息

    # 尺寸常量
    HIDDEN_W = 60
    HIDDEN_H = 4
    NOTIFY_W = 280
    NOTIFY_H = 56
    INTERACTIVE_W = 380
    INTERACTIVE_H = 480

    def __init__(self):
        super().__init__()
        self._state = State.HIDDEN
        self._current_session_id = ""
        self._history_bubbles: list[MessageBubble] = []
        self._current_bubble: MessageBubble | None = None
        self._seq = 0
        self._dragging = False
        self._drag_start = QPoint()
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._to_hidden)

        self._init_ui()
        self._restore_position()

    # ── 初始化 ──

    def _init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # 主布局
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # ── 通知标签（通知态显示）──
        self._notify_label = QLabel()
        self._notify_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notify_label.setWordWrap(True)
        self._notify_label.setStyleSheet(
            "color: #e0e0e0; font-size: 14px; padding: 12px 16px; background: transparent;"
        )
        self._main_layout.addWidget(self._notify_label)

        # ── 滚动区域（交互态显示）──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: #333; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 2px; }"
        )
        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll_layout.setSpacing(6)
        self._scroll_layout.setContentsMargins(12, 12, 12, 12)
        self._scroll.setWidget(self._scroll_content)
        self._main_layout.addWidget(self._scroll)

        # ── 底部 spacer（把内容往上推）──
        self._scroll_layout.addStretch()

        # ── 输入区域（交互态显示）──
        self._input_row = QWidget()
        input_layout = QHBoxLayout(self._input_row)
        input_layout.setContentsMargins(12, 8, 12, 12)

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("输入消息...")
        self._input_field.setStyleSheet(
            "QLineEdit {"
            "  background: #2a2a2a; color: #e0e0e0; border: 1px solid #444;"
            "  border-radius: 8px; padding: 8px 12px; font-size: 13px;"
            "}"
            "QLineEdit:focus { border-color: #666; }"
        )
        self._input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self._input_field)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedSize(60, 34)
        self._send_btn.setStyleSheet(
            "QPushButton {"
            "  background: #3a3a3a; color: #e0e0e0; border: 1px solid #555;"
            "  border-radius: 8px; font-size: 13px;"
            "}"
            "QPushButton:hover { background: #4a4a4a; }"
        )
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        self._main_layout.addWidget(self._input_row)

        # ── opacity 效果 ──
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.85)
        self.setGraphicsEffect(self._opacity)

        # 初始状态
        self._apply_state()

    def _restore_position(self):
        x = int(get("panel/x") or -1)
        y = 0
        if x < 0:
            screen = QApplication.primaryScreen().availableGeometry()
            x = (screen.width() - self.HIDDEN_W) // 2

        delay = int(get("panel/hide_delay_ms") or DEFAULTS["panel/hide_delay_ms"])
        self._hide_timer.setInterval(delay)

        self.setGeometry(x, y, self.HIDDEN_W, self.HIDDEN_H)
        self.show()

    # ── 状态切换 ──

    def _apply_state(self):
        """根据当前状态设置可见性和尺寸。"""
        x = self.x()
        y = self.y()

        hide_delay = int(get("panel/hide_delay_ms") or DEFAULTS["panel/hide_delay_ms"])

        if self._state == State.HIDDEN:
            target_rect = QRect(x, y, self.HIDDEN_W, self.HIDDEN_H)
            self._notify_label.setVisible(False)
            self._scroll.setVisible(False)
            self._input_row.setVisible(False)
            self._hide_timer.stop()

        elif self._state == State.NOTIFY:
            target_rect = QRect(x, y, self.NOTIFY_W, self.NOTIFY_H)
            self._notify_label.setVisible(True)
            self._scroll.setVisible(False)
            self._input_row.setVisible(False)
            self._hide_timer.start(hide_delay)

        else:  # INTERACTIVE
            target_rect = QRect(x, y, self.INTERACTIVE_W, self.INTERACTIVE_H)
            self._notify_label.setVisible(False)
            self._scroll.setVisible(True)
            self._input_row.setVisible(True)
            self._hide_timer.stop()

        # 动画过渡
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(150)
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target_rect)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _to_hidden(self):
        self._state = State.HIDDEN
        self._apply_state()

    # ── 外部接口 ──

    def show_notification(self, text: str):
        """显示通知。收起态直接显示，其他状态不打断。"""
        self._notify_label.setText(text[:120])  # 截断长文本
        if self._state == State.HIDDEN:
            self._state = State.NOTIFY
            self._apply_state()

    def start_response(self):
        """开始一次 Agent 回复流。"""
        self._current_bubble = MessageBubble("assistant", "", self._scroll_content)
        self._scroll_layout.insertWidget(
            self._scroll_layout.count() - 1,  # 在 stretch 之前
            self._current_bubble,
        )
        self._history_bubbles.append(self._current_bubble)
        self._seq = 0

    def append_delta(self, text: str):
        """追加流式片段。"""
        if self._current_bubble:
            self._current_bubble.append_text(text)

    def end_response(self, session_id: str = ""):
        """Agent 回复完成。"""
        self._current_session_id = session_id or self._current_session_id
        self._current_bubble = None

    def show_system_notification(self, text: str):
        """显示系统通知（后台任务等）。"""
        self.show_notification(text)

    def show_error(self, text: str):
        """显示错误。"""
        bubble = MessageBubble("assistant", f"❌ {text}", self._scroll_content)
        self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, bubble)
        self._history_bubbles.append(bubble)

    def add_user_message(self, text: str):
        """在历史中添加用户消息气泡。"""
        bubble = MessageBubble("user", text, self._scroll_content)
        self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, bubble)
        self._history_bubbles.append(bubble)

    def load_history(self, messages: list[dict]):
        """从数据库加载历史消息。"""
        for msg in messages:
            bubble = MessageBubble(msg["role"], msg["content"], self._scroll_content)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, bubble)
            self._history_bubbles.append(bubble)

    def clear_history_ui(self):
        """清除 UI 中的历史气泡。"""
        for bubble in self._history_bubbles:
            bubble.deleteLater()
        self._history_bubbles.clear()
        self._current_bubble = None

    def set_connected(self, connected: bool):
        """更新连接状态（可选：改变指示器颜色）。"""
        pass

    # ── 事件处理 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._state in (State.HIDDEN, State.NOTIFY):
                # 点击切换到交互态
                self._state = State.INTERACTIVE
                self._apply_state()
                # 滚动到底部
                scrollbar = self._scroll.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            else:
                # 交互态中：开始拖拽
                self._dragging = True
                self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_start
            # 限制 Y 坐标在顶部区域
            new_pos.setY(max(0, min(new_pos.y(), 50)))
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            # 持久化位置
            set_("panel/x", self.x())
            set_("panel/y", 0)

    def enterEvent(self, event):
        """鼠标进入面板区域。"""
        if self._state == State.NOTIFY:
            self._hide_timer.stop()

    def leaveEvent(self, event):
        """鼠标离开面板区域。"""
        if self._state == State.NOTIFY:
            delay = int(get("panel/hide_delay_ms") or 5000)
            self._hide_timer.start(delay)

    def paintEvent(self, event):
        """绘制黑色圆角矩形背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._state != State.HIDDEN:
            rect = self.rect()
            painter.setBrush(QBrush(QColor(30, 30, 30, 230)))
            painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, 0, 0), 18, 18)

        painter.end()

    # ── 内部 ──

    def _send_message(self):
        text = self._input_field.text().strip()
        if not text:
            return
        self._input_field.clear()
        self.add_user_message(text)
        self.message_sent.emit(text)
```

---

### Task 7: 系统托盘

**文件：**
- 创建：`hermes_panel/tray.py`

```python
"""hermes_panel/tray.py - 系统托盘管理。"""
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def _resource_path(filename: str) -> str:
    """获取资源文件路径。"""
    base = Path(__file__).parent / "resources"
    return str(base / filename)


class TrayManager(QSystemTrayIcon):
    """系统托盘管理。

    提供托盘图标、右键菜单（显示/隐藏面板、设置、退出）。
    """

    show_panel_requested = pyqtSignal()
    hide_panel_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        icon_path = _resource_path("icon.png")
        if Path(icon_path).exists():
            self.setIcon(QIcon(icon_path))
        else:
            # 降级：用内置 emoji 图标
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))
            p = QPainter(pixmap)
            p.setPen(QColor(200, 200, 200))
            p.drawText(pixmap.rect(), 0x1004, "H")  # Qt.AlignCenter
            p.end()
            self.setIcon(QIcon(pixmap))

        self.setToolTip("Hermes Desktop Panel")

        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)

        self.show()

    def _build_menu(self):
        show_action = QAction("显示/隐藏面板")
        show_action.triggered.connect(self.show_panel_requested.emit)
        self._menu.addAction(show_action)

        self._menu.addSeparator()

        settings_action = QAction("设置")
        settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("退出")
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)
```

---

### Task 8: 设置对话框

**文件：**
- 创建：`hermes_panel/settings_dialog.py`

```python
"""hermes_panel/settings_dialog.py - 设置对话框。"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QPushButton, QGroupBox, QLabel,
)

from hermes_panel.config import get, set_, SETTINGS


class SettingsDialog(QDialog):
    """设置对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hermes Panel 设置")
        self.setMinimumWidth(400)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── 服务器 ──
        server_group = QGroupBox("服务器连接")
        server_form = QFormLayout()

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("127.0.0.1")
        server_form.addRow("主机地址:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(8643)
        server_form.addRow("端口:", self._port_input)

        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("输入认证 token")
        server_form.addRow("Token:", self._token_input)

        self._tls_check = QCheckBox("启用 TLS (wss://)")
        server_form.addRow(self._tls_check)

        self._verify_cert_check = QCheckBox("验证 TLS 证书")
        server_form.addRow(self._verify_cert_check)

        server_group.setLayout(server_form)
        layout.addWidget(server_group)

        # ── 面板 ──
        panel_group = QGroupBox("面板行为")
        panel_form = QFormLayout()

        self._hide_delay = QSpinBox()
        self._hide_delay.setRange(1000, 30000)
        self._hide_delay.setSuffix(" ms")
        self._hide_delay.setSingleStep(500)
        panel_form.addRow("自动隐藏延迟:", self._hide_delay)

        panel_group.setLayout(panel_form)
        layout.addWidget(panel_group)

        # ── 系统 ──
        system_group = QGroupBox("系统")
        system_form = QFormLayout()

        self._autostart_check = QCheckBox("开机自启")
        system_form.addRow(self._autostart_check)

        system_group.setLayout(system_form)
        layout.addWidget(system_group)

        # ── 按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _load_values(self):
        self._host_input.setText(get("server/host"))
        self._port_input.setValue(int(get("server/port") or 8643))
        self._token_input.setText(get("server/token"))
        self._tls_check.setChecked(get("server/tls").lower() in ("true", "1", "yes"))
        self._verify_cert_check.setChecked(get("server/verify_cert").lower() in ("true", "1", "yes"))
        self._hide_delay.setValue(int(get("panel/hide_delay_ms") or 5000))
        self._autostart_check.setChecked(get("app/autostart").lower() in ("true", "1", "yes"))

    def _save(self):
        set_("server/host", self._host_input.text())
        set_("server/port", self._port_input.value())
        set_("server/token", self._token_input.text())
        set_("server/tls", self._tls_check.isChecked())
        set_("server/verify_cert", self._verify_cert_check.isChecked())
        set_("panel/hide_delay_ms", self._hide_delay.value())
        set_("app/autostart", self._autostart_check.isChecked())

        self._apply_autostart(self._autostart_check.isChecked())
        self.accept()

    def _apply_autostart(self, enable: bool):
        """设置 Windows 开机自启。"""
        import sys
        if sys.platform != "win32":
            return

        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
        except OSError:
            return

        if enable:
            exe_path = sys.executable
            script_path = sys.argv[0]
            winreg.SetValueEx(key, "HermesPanel", 0, winreg.REG_SZ, f'"{exe_path}" "{script_path}"')
        else:
            try:
                winreg.DeleteValue(key, "HermesPanel")
            except OSError:
                pass
        winreg.CloseKey(key)
```

---

### Task 9: 样式表

**文件：**
- 创建：`hermes_panel/resources/styles.qss`

```css
/* 全局样式 - 暗色主题 */
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}

QScrollArea {
    border: none;
    background: transparent;
}
```

---

### Task 10: 主入口

**文件：**
- 创建：`main.py`

```python
"""main.py - Hermes Desktop Panel 入口。"""
import sys
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from hermes_panel.config import get
from hermes_panel.client import HermesClient
from hermes_panel.store import MessageStore
from hermes_panel.tray import TrayManager
from hermes_panel.panel import HermesPanel
from hermes_panel.settings_dialog import SettingsDialog


def _get_db_path() -> str:
    """获取数据库路径。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(base, "HermesPanel")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        db_dir = os.path.join(base, "hermes-panel")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "messages.db")


class Application:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # 加载样式
        from pathlib import Path
        style_path = Path(__file__).parent / "hermes_panel" / "resources" / "styles.qss"
        if style_path.exists():
            self._app.setStyleSheet(style_path.read_text(encoding="utf-8"))

        # 核心组件
        self._store = MessageStore(_get_db_path())
        self._client = HermesClient()
        self._panel = HermesPanel()
        self._tray = TrayManager()

        self._connect_signals()
        self._connect_to_server()
        self._load_history()

    def _connect_signals(self):
        # 面板 → 客户端
        self._panel.message_sent.connect(self._client.send_message)

        # 客户端 → 面板
        self._client.delta_received.connect(self._on_delta)
        self._client.done_received.connect(self._on_done)
        self._client.notification_received.connect(self._on_notification)
        self._client.error_occurred.connect(self._on_error)
        self._client.connected.connect(self._on_connected)
        self._client.disconnected.connect(self._on_disconnected)
        self._client.auth_ok.connect(lambda: self._panel.set_connected(True))

        # 托盘
        self._tray.show_panel_requested.connect(self._toggle_panel)
        self._tray.settings_requested.connect(self._show_settings)
        self._tray.quit_requested.connect(self._quit)

    def _connect_to_server(self):
        host = get("server/host")
        port = int(get("server/port") or 8643)
        token = get("server/token")
        tls = get("server/tls").lower() in ("true", "1", "yes")
        verify_cert = get("server/verify_cert").lower() in ("true", "1", "yes")

        if token:
            self._client.connect_to_server(host, port, token, tls, verify_cert)
        else:
            # 无 token：显示提示
            self._panel.show_error("请先在设置中配置服务器 token")

    def _load_history(self):
        try:
            msgs = self._store.get_messages(limit=50)
            if msgs:
                self._panel.load_history(msgs)
        except Exception:
            pass

    # ── 回调 ──

    def _on_delta(self, text: str, seq: int):
        if seq == 0:
            self._panel.start_response()
        self._panel.append_delta(text)

    def _on_done(self, session_id: str):
        self._panel.end_response(session_id)
        # 保存到数据库
        self._store.save_message("assistant", self._get_last_assistant_text(), session_id)

    def _on_notification(self, text: str, level: str):
        self._panel.show_system_notification(text)

    def _on_error(self, text: str):
        self._panel.show_error(text)

    def _on_connected(self):
        pass  # 等待 auth_ok

    def _on_disconnected(self):
        self._panel.set_connected(False)

    def _toggle_panel(self):
        # 简单切换显示/隐藏动画
        pass

    def _show_settings(self):
        dialog = SettingsDialog()
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            # 重新连接
            self._client.disconnect()
            self._connect_to_server()

    def _get_last_assistant_text(self) -> str:
        """获取最后一条助手消息文本（从 UI 气泡中读取）。"""
        bubbles = self._panel._history_bubbles
        for bubble in reversed(bubbles):
            if bubble.role() == "assistant":
                return bubble._label.text()
        return ""

    def _quit(self):
        self._client.disconnect()
        self._store.close()
        self._app.quit()

    def run(self):
        return self._app.exec()


def main():
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
```

---

### Task 11: PyInstaller 打包脚本

**文件：**
- 创建：`scripts/build_exe.py`

```python
"""scripts/build_exe.py - PyInstaller 打包脚本。"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "HermesPanel",
    "--onefile",
    "--windowed",
    "--noconsole",
    "--add-data", f"hermes_panel/resources{';'}hermes_panel/resources",
    str(PROJECT_ROOT / "main.py"),
]

subprocess.run(cmd, cwd=str(PROJECT_ROOT))
```

对应的 requirements.txt 中追加：
```
pyinstaller>=6.0.0
```

---

### Task 12: 连接测试与代码审查

**Step 1: 单元测试**
```bash
pytest tests/ -v
```

**Step 2: 服务端适配器测试**

在 Hermes 仓库中运行网关，验证桌面适配器启动：
```bash
hermes gateway start
# 检查日志: [desktop] Listening on ws://0.0.0.0:8643/ws
```

**Step 3: 联调测试**

1. 启动桌面组件
2. 在设置中配置正确的服务器地址和 token
3. 验证 WebSocket 连接成功
4. 发送消息验证 Agent 流式回复
5. 验证通知展示、拖拽、自适应隐藏

**Step 4: 代码审查**

使用 @oracle 审查所有文件：
- `hermes_panel/protocol.py` — 消息协议完整性
- `hermes_panel/client.py` — 重连逻辑和线程安全
- `hermes_panel/panel.py` — UI 状态机正确性
- `hermes_panel/store.py` — SQLite 安全性
- `gateway/platforms/desktop.py` — 适配器接口一致性

---

## 总结

| 文件 | 行数估计 | 说明 |
|------|---------|------|
| `gateway/platforms/desktop.py` | ~250 | Hermes 服务端适配器 |
| `hermes_panel/protocol.py` | ~100 | 消息协议 |
| `hermes_panel/client.py` | ~140 | WebSocket 客户端 |
| `hermes_panel/panel.py` | ~350 | 灵动岛面板 UI |
| `hermes_panel/tray.py` | ~80 | 系统托盘 |
| `hermes_panel/settings_dialog.py` | ~170 | 设置对话框 |
| `hermes_panel/store.py` | ~70 | SQLite 存储 |
| `hermes_panel/config.py` | ~30 | 配置管理 |
| `main.py` | ~160 | 主入口 |
| `tests/` | ~100 | 单元测试 |
| **合计** | **~1450** | |
