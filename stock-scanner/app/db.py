"""SQLite persistence for saved custom strategies (parameterised queries only)."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_settings

MAX_SAVED = 100


@contextmanager
def connect():
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - non-POSIX filesystems
        pass


def init_db() -> None:
    with connect() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS custom_strategies (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL UNIQUE,
                   definition TEXT NOT NULL,
                   created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )


def ping() -> bool:
    with connect() as c:
        c.execute("SELECT 1").fetchone()
    return True


def list_strategies() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT name, definition, created_at FROM custom_strategies ORDER BY name").fetchall()
    return [{**json.loads(r["definition"]), "created_at": r["created_at"]} for r in rows]


def get_strategy(name: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT definition FROM custom_strategies WHERE name = ?", (name,)).fetchone()
    return json.loads(r["definition"]) if r else None


def save_strategy(name: str, definition: dict) -> None:
    with connect() as c:
        exists = c.execute("SELECT 1 FROM custom_strategies WHERE name = ?", (name,)).fetchone()
        count = c.execute("SELECT COUNT(*) FROM custom_strategies").fetchone()[0]
        if not exists and count >= MAX_SAVED:
            raise ValueError(f"Limit of {MAX_SAVED} saved strategies reached")
        c.execute(
            """INSERT INTO custom_strategies (name, definition) VALUES (?, ?)
               ON CONFLICT(name) DO UPDATE SET definition = excluded.definition""",
            (name, json.dumps(definition, separators=(",", ":"))),
        )


def delete_strategy(name: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM custom_strategies WHERE name = ?", (name,))
        return cur.rowcount > 0
