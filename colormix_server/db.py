"""登録データの保存先 (SQLite)。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS registrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instagram   TEXT NOT NULL UNIQUE,
    affiliation TEXT NOT NULL,
    salon       TEXT NOT NULL DEFAULT '',
    lang        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_registration(path: str, record: dict) -> tuple[dict, bool]:
    """登録を保存する。

    同じ Instagram アカウントが既にあれば内容を更新する(重複行は作らない)。

    :returns: (保存後の行, 新規なら True)
    """
    now = _now()
    with connect(path) as conn:
        existing = conn.execute(
            "SELECT id FROM registrations WHERE instagram = ?", (record["instagram"],)
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO registrations
                    (instagram, affiliation, salon, lang, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record["instagram"],
                    record["affiliation"],
                    record["salon"],
                    record["lang"],
                    now,
                    now,
                ),
            )
            created = True
        else:
            conn.execute(
                """
                UPDATE registrations
                   SET affiliation = ?, salon = ?, lang = ?, updated_at = ?
                 WHERE instagram = ?
                """,
                (
                    record["affiliation"],
                    record["salon"],
                    record["lang"],
                    now,
                    record["instagram"],
                ),
            )
            created = False

        row = conn.execute(
            "SELECT * FROM registrations WHERE instagram = ?", (record["instagram"],)
        ).fetchone()

    return dict(row), created


def list_registrations(path: str) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM registrations ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def count_by_affiliation(path: str) -> dict:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT affiliation, COUNT(*) AS n FROM registrations GROUP BY affiliation"
        ).fetchall()
    counts = {row["affiliation"]: row["n"] for row in rows}
    counts["total"] = sum(counts.values())
    return counts
