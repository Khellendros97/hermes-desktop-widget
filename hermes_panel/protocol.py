"""Message protocol for WebSocket communication with Hermes desktop adapter.

Defines all message types and serialization/deserialization logic.
"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class OutgoingMessage:
    """Client -> Server message."""
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
    """Server -> Client: streaming response fragment."""
    text: str
    seq: int = 0


@dataclass
class IncomingDone:
    """Server -> Client: conversation turn complete."""
    session_id: str = ""


@dataclass
class IncomingNotification:
    """Server -> Client: system notification (cron results, etc.)."""
    text: str
    level: str = "info"
    style: str = ""


@dataclass
class IncomingError:
    """Server -> Client: error message."""
    text: str


@dataclass
class IncomingAuthOk:
    """Server -> Client: authentication successful."""
    pass


_TYPE_MAP = {
    "delta": IncomingDelta,
    "done": IncomingDone,
    "notification": IncomingNotification,
    "error": IncomingError,
    "auth_ok": IncomingAuthOk,
}


def deserialize(raw: str):
    """Parse JSON string into a typed message object. Returns None for unknown types."""
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
        return cls(text=data.get("text", ""), level=data.get("level", "info"), style=data.get("style", ""))
    elif cls is IncomingError:
        return cls(text=data.get("text", ""))
    elif cls is IncomingAuthOk:
        return cls()
    return None
