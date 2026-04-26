"""SQLite message store for persisting chat history locally."""

import sqlite3
from typing import Optional


class MessageStore:
    """Persistent message storage backed by SQLite."""

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

    def get_messages(self, session_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        msgs = [dict(r) for r in rows]
        msgs.reverse()
        return msgs

    def clear_messages(self):
        self._conn.execute("DELETE FROM messages")
        self._conn.commit()

    def close(self):
        self._conn.close()
