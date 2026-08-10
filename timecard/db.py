"""SQLite を使ったデータアクセス層。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .attendance import Punch

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS punches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    punch_type  TEXT    NOT NULL,
    punched_at  TEXT    NOT NULL,
    note        TEXT,
    FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_punches_employee_time
    ON punches (employee_id, punched_at);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """接続を生成する。行を辞書ライクに扱えるようにする。"""
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---- 社員 ------------------------------------------------------------------

def create_employee(conn: sqlite3.Connection, code: str, name: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO employees (code, name, created_at) VALUES (?, ?, ?)",
        (code, name, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_employees(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM employees ORDER BY code"
    ).fetchall()


def get_employee(conn: sqlite3.Connection, employee_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()


def delete_employee(conn: sqlite3.Connection, employee_id: int) -> None:
    conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    conn.commit()


# ---- 打刻 ------------------------------------------------------------------

def add_punch(
    conn: sqlite3.Connection,
    employee_id: int,
    punch_type: str,
    punched_at: datetime,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO punches (employee_id, punch_type, punched_at, note) "
        "VALUES (?, ?, ?, ?)",
        (employee_id, punch_type, punched_at.isoformat(timespec="seconds"), note),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_punches(
    conn: sqlite3.Connection,
    employee_id: int,
    date_prefix: str | None = None,
) -> list[Punch]:
    """社員の打刻を取得する。date_prefix('YYYY-MM' や 'YYYY-MM-DD')で絞り込み。"""
    sql = "SELECT punch_type, punched_at FROM punches WHERE employee_id = ?"
    params: list[object] = [employee_id]
    if date_prefix:
        sql += " AND punched_at LIKE ?"
        params.append(f"{date_prefix}%")
    sql += " ORDER BY punched_at"
    rows = conn.execute(sql, params).fetchall()
    return [
        Punch(punch_type=r["punch_type"], punched_at=datetime.fromisoformat(r["punched_at"]))
        for r in rows
    ]


def get_punch_rows(
    conn: sqlite3.Connection,
    employee_id: int,
    date_prefix: str | None = None,
) -> list[sqlite3.Row]:
    """UI 表示用に id や note を含む生の行を取得する。"""
    sql = "SELECT * FROM punches WHERE employee_id = ?"
    params: list[object] = [employee_id]
    if date_prefix:
        sql += " AND punched_at LIKE ?"
        params.append(f"{date_prefix}%")
    sql += " ORDER BY punched_at"
    return conn.execute(sql, params).fetchall()
