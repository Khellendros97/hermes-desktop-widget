"""Tests for protocol module."""

import json
import pytest
from hermes_panel.protocol import (
    OutgoingMessage, IncomingDelta, IncomingDone,
    IncomingNotification, IncomingError, IncomingAuthOk,
    deserialize,
)


def test_outgoing_message_serialize():
    msg = OutgoingMessage(text="hello")
    assert msg.to_dict() == {"type": "message", "text": "hello"}


def test_outgoing_auth_serialize():
    msg = OutgoingMessage(type_="auth", token="secret")
    assert msg.to_dict() == {"type": "auth", "token": "secret"}


def test_outgoing_ping_serialize():
    msg = OutgoingMessage(type_="ping")
    assert msg.to_dict() == {"type": "ping"}


def test_deserialize_delta():
    raw = json.dumps({"type": "delta", "text": "hello world", "seq": 3})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingDelta)
    assert msg.text == "hello world"
    assert msg.seq == 3


def test_deserialize_done():
    raw = json.dumps({"type": "done", "session_id": "abc123"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingDone)
    assert msg.session_id == "abc123"


def test_deserialize_notification():
    raw = json.dumps({"type": "notification", "text": "task done", "level": "info"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingNotification)
    assert msg.text == "task done"
    assert msg.level == "info"


def test_deserialize_error():
    raw = json.dumps({"type": "error", "text": "auth failed"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingError)
    assert msg.text == "auth failed"


def test_deserialize_auth_ok():
    raw = json.dumps({"type": "auth_ok"})
    msg = deserialize(raw)
    assert isinstance(msg, IncomingAuthOk)


def test_deserialize_unknown():
    raw = json.dumps({"type": "unknown", "data": 42})
    msg = deserialize(raw)
    assert msg is None


def test_deserialize_invalid_json():
    msg = deserialize("not json")
    assert msg is None
