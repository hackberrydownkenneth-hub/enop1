"""SQLite を使ったデータアクセス層(財務・経営指標システム専用の DB)。

タイムカードシステムとは別のデータベースファイルを使う。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .calc import SOURCE_MANUAL, Entry
from .kpi import MonthlyInputs

SCHEMA = """
CREATE TABLE IF NOT EXISTS fin_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    month      TEXT    NOT NULL,           -- 対象月 YYYY-MM
    category   TEXT    NOT NULL,           -- calc.CATEGORY_LABELS のキー
    item       TEXT    NOT NULL,           -- 科目名
    amount     INTEGER NOT NULL,           -- 金額(セント)
    memo       TEXT,
    source     TEXT    NOT NULL DEFAULT 'manual',  -- manual / import
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

CREATE TABLE IF NOT EXISTS kpi_inputs (
    month        TEXT    PRIMARY KEY,      -- 対象月 YYYY-MM
    customers    INTEGER NOT NULL DEFAULT 0,  -- 客数
    open_days    INTEGER NOT NULL DEFAULT 0,  -- 営業日数
    cash_balance INTEGER,                     -- 現金残高(セント)。NULL なら BS から推定
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS startup_costs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item       TEXT    NOT NULL,           -- 内装工事・厨房機器・保証金 など
    amount     INTEGER NOT NULL,           -- 金額(セント)
    month      TEXT,                       -- 支出した月 YYYY-MM(任意)
    memo       TEXT,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,           -- 2 号店出店・設備更新 など
    amount     INTEGER NOT NULL,           -- 必要額(セント)
    memo       TEXT,
    created_at TEXT    NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
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
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(fin_entries)")}
    if "source" not in cols:
        conn.execute(
            "ALTER TABLE fin_entries ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        )


# ---- PL / BS の明細 --------------------------------------------------------

def add_entry(
    conn: sqlite3.Connection,
    month: str,
    category: str,
    item: str,
    amount: int,
    memo: str | None = None,
    source: str = SOURCE_MANUAL,
) -> int:
    """明細を 1 件登録する。amount はセント。"""
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO fin_entries (month, category, item, amount, memo, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (month, category, item, amount, memo, source, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_entry(conn: sqlite3.Connection, entry_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM fin_entries WHERE id = ?", (entry_id,)).fetchone()


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM fin_entries WHERE id = ?", (entry_id,))
    conn.commit()


def delete_entries_by_source(conn: sqlite3.Connection, month: str, source: str) -> int:
    """取り込み由来の明細をまとめて削除する(再取り込み時の重複防止)。"""
    cur = conn.execute(
        "DELETE FROM fin_entries WHERE month = ? AND source = ?", (month, source)
    )
    conn.commit()
    return cur.rowcount


def list_entries(
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


def list_months(conn: sqlite3.Connection) -> list[str]:
    """データが登録されている月を新しい順に返す。"""
    rows = conn.execute(
        "SELECT month FROM fin_entries UNION SELECT month FROM kpi_inputs "
        "ORDER BY month DESC"
    )
    return [row["month"] for row in rows]


def copy_entries(
    conn: sqlite3.Connection,
    from_month: str,
    to_month: str,
    categories: tuple[str, ...] | None = None,
) -> int:
    """前月などの明細を対象月に複製する。複製した件数を返す。"""
    entries = list_entries(conn, from_month, categories)
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO fin_entries (month, category, item, amount, memo, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (to_month, e.category, e.item, e.amount, e.memo or None, e.source, now)
            for e in entries
        ],
    )
    conn.commit()
    return len(entries)


# ---- 月次目標 --------------------------------------------------------------

def get_target(conn: sqlite3.Connection, month: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM fin_targets WHERE month = ?", (month,)).fetchone()


def set_target(
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


# ---- 手入力の月次指標 ------------------------------------------------------

def get_inputs(conn: sqlite3.Connection, month: str) -> MonthlyInputs:
    """客数・営業日数・現金残高。未登録なら空の値を返す。"""
    row = conn.execute("SELECT * FROM kpi_inputs WHERE month = ?", (month,)).fetchone()
    if row is None:
        return MonthlyInputs()
    return MonthlyInputs(
        customers=row["customers"],
        open_days=row["open_days"],
        cash_balance=row["cash_balance"],
    )


def set_inputs(
    conn: sqlite3.Connection,
    month: str,
    customers: int,
    open_days: int,
    cash_balance: int | None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO kpi_inputs (month, customers, open_days, cash_balance, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(month) DO UPDATE SET "
        "customers = excluded.customers, open_days = excluded.open_days, "
        "cash_balance = excluded.cash_balance, updated_at = excluded.updated_at",
        (month, customers, open_days, cash_balance, now),
    )
    conn.commit()


def _to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        category=row["category"],
        item=row["item"],
        amount=row["amount"],
        memo=row["memo"] or "",
        source=row["source"],
    )


# ---- オープンコスト(初期投資) --------------------------------------------

def add_startup_cost(
    conn: sqlite3.Connection,
    item: str,
    amount: int,
    month: str | None = None,
    memo: str | None = None,
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO startup_costs (item, amount, month, memo, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (item, amount, month, memo, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_startup_cost(conn: sqlite3.Connection, cost_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM startup_costs WHERE id = ?", (cost_id,)
    ).fetchone()


def delete_startup_cost(conn: sqlite3.Connection, cost_id: int) -> None:
    conn.execute("DELETE FROM startup_costs WHERE id = ?", (cost_id,))
    conn.commit()


def list_startup_costs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM startup_costs ORDER BY id").fetchall()


def total_startup_cost(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM startup_costs").fetchone()
    return int(row["total"])


# ---- 次にやれること(投資計画) --------------------------------------------

def add_plan(
    conn: sqlite3.Connection, name: str, amount: int, memo: str | None = None
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO plans (name, amount, memo, created_at) VALUES (?, ?, ?, ?)",
        (name, amount, memo, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_plan(conn: sqlite3.Connection, plan_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def delete_plan(conn: sqlite3.Connection, plan_id: int) -> None:
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()


def list_plans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM plans ORDER BY amount").fetchall()
