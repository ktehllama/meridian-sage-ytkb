"""
api/chat_db.py
==============
SQLite CRUD for chat history stored in chats.db (separate from knowledge.db).
"""

import json
import logging
import sqlite3

from api.config import config

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(config.CHATS_DB_PATH)


def init_db() -> None:
    """Create chats and settings tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id       TEXT    PRIMARY KEY,
                name     TEXT    NOT NULL,
                mode     TEXT    NOT NULL DEFAULT 'ephemeral',
                messages TEXT    NOT NULL,
                saved_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_saved_at ON chats(saved_at)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Chat DB ready.")


def get_setting(key: str, default: str = '') -> str:
    with _get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with _get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        conn.commit()


def upsert_chat(id: str, name: str, mode: str, messages: list, saved_at: int) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chats (id, name, mode, messages, saved_at) VALUES (?,?,?,?,?)",
            (id, name, mode, json.dumps(messages), saved_at),
        )
        conn.commit()


def list_chats() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, mode, messages, saved_at FROM chats ORDER BY saved_at DESC LIMIT 50"
        ).fetchall()
    return [
        {"id": r[0], "name": r[1], "mode": r[2], "messages": json.loads(r[3]), "savedAt": r[4]}
        for r in rows
    ]


def delete_chat(chat_id: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        conn.commit()


def rename_chat(chat_id: str, name: str) -> None:
    with _get_conn() as conn:
        conn.execute("UPDATE chats SET name = ? WHERE id = ?", (name, chat_id))
        conn.commit()
