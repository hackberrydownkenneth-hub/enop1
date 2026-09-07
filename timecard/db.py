"""SQLite を使ったデータアクセス層。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .attendance import Punch
from .finance import Entry

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    name         TEXT    NOT NULL,
    hourly_wage  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
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

CREATE TABLE IF NOT EXISTS fin_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    month      TEXT    NOT NULL,           -- 対象月 YYYY-MM
    category   TEXT    NOT NULL,           -- finance.CATEGORY_LABELS のキー
    item       TEXT    NOT NULL,           -- 科目名
    amount     INTEGER NOT NULL,           -- 金額(セント)
    memo       TEXT,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fin_entries_month
    ON fin_entries (month, category);

CREATE TABLE IF NOT EXISTS fin_targets (
    month      TEXT    PRIMARY KEY,        -- 対象月 YYYY-MM
    target_min INTEGER NOT NULL,           -- 目標下限(セント)
    target_max INTEGER NOT NULL,           -- 目標上限(セント)
    updated_at TEXT    NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """接続を生成する。行を辞書ライクに扱えるようにする。"""
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """既存 DB に不足しているカラムを追加する簡易マイグレーション。"""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
    if "hourly_wage" not in cols:
        conn.execute(
            "ALTER TABLE employees ADD COLUMN hourly_wage INTEGER NOT NULL DEFAULT 0"
        )


# ---- 社員 ------------------------------------------------------------------

def create_employee(
    conn: sqlite3.Connection, code: str, name: str, hourly_wage: int = 0
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO employees (code, name, hourly_wage, created_at) "
        "VALUES (?, ?, ?, ?)",
        (code, name, hourly_wage, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_wage(conn: sqlite3.Connection, employee_id: int, hourly_wage: int) -> None:
    conn.execute(
        "UPDATE employees SET hourly_wage = ? WHERE id = ?",
        (hourly_wage, employee_id),
    )
    conn.commit()


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


# ---- PL / BS ---------------------------------------------------------------

def add_fin_entry(
    conn: sqlite3.Connection,
    month: str,
    category: str,
    item: str,
    amount: int,
    memo: str | None = None,
) -> int:
    """PL / BS の明細を 1 件登録する。amount はセント。"""
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO fin_entries (month, category, item, amount, memo, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (month, category, item, amount, memo, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_fin_entry(conn: sqlite3.Connection, entry_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM fin_entries WHERE id = ?", (entry_id,)
    ).fetchone()


def update_fin_entry(
    conn: sqlite3.Connection,
    entry_id: int,
    item: str,
    amount: int,
    memo: str | None = None,
) -> None:
    conn.execute(
        "UPDATE fin_entries SET item = ?, amount = ?, memo = ? WHERE id = ?",
        (item, amount, memo, entry_id),
    )
    conn.commit()


def delete_fin_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM fin_entries WHERE id = ?", (entry_id,))
    conn.commit()


def list_fin_entries(
    conn: sqlite3.Connection, month: str, categories: tuple[str, ...] | None = None
) -> list[Entry]:
    """対象月の明細を取得する。categories を渡すとそのカテゴリのみ。"""
    sql = "SELECT * FROM fin_entries WHERE month = ?"
    params: list[object] = [month]
    if categories:
        placeholders = ", ".join("?" for _ in categories)
        sql += f" AND category IN ({placeholders})"
        params.extend(categories)
    sql += " ORDER BY id"
    return [_to_entry(row) for row in conn.execute(sql, params)]


def list_fin_months(conn: sqlite3.Connection) -> list[str]:
    """明細が登録されている月を新しい順に返す。"""
    return [
        row["month"]
        for row in conn.execute(
            "SELECT DISTINCT month FROM fin_entries ORDER BY month DESC"
        )
    ]


def copy_fin_entries(
    conn: sqlite3.Connection,
    from_month: str,
    to_month: str,
    categories: tuple[str, ...] | None = None,
) -> int:
    """前月などの明細を対象月に複製する。複製した件数を返す。"""
    entries = list_fin_entries(conn, from_month, categories)
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO fin_entries (month, category, item, amount, memo, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (to_month, e.category, e.item, e.amount, e.memo or None, now)
            for e in entries
        ],
    )
    conn.commit()
    return len(entries)


def get_fin_target(conn: sqlite3.Connection, month: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM fin_targets WHERE month = ?", (month,)
    ).fetchone()


def set_fin_target(
    conn: sqlite3.Connection, month: str, target_min: int, target_max: int
) -> None:
    """月次の目標利益(セント)を保存する。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO fin_targets (month, target_min, target_max, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(month) DO UPDATE SET "
        "target_min = excluded.target_min, target_max = excluded.target_max, "
        "updated_at = excluded.updated_at",
        (month, target_min, target_max, now),
    )
    conn.commit()


def _to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        category=row["category"],
        item=row["item"],
        amount=row["amount"],
        memo=row["memo"] or "",
    )
