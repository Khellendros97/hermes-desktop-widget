"""Tests for store module."""

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
    store.save_message("user", "hello")
    store.save_message("assistant", "hi there")

    messages = store.get_messages(limit=10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
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
