"""勤怠計算のドメインロジック(純粋関数)。

このモジュールはデータベースや Web フレームワークに依存しない。
打刻イベントのリストを受け取り、勤務時間・休憩時間・残業などを算出する。
そのためユニットテストが容易になっている。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# 打刻種別
PUNCH_IN = "in"            # 出勤
PUNCH_OUT = "out"          # 退勤
BREAK_IN = "break_in"      # 休憩開始
BREAK_OUT = "break_out"    # 休憩終了

PUNCH_TYPES = (PUNCH_IN, PUNCH_OUT, BREAK_IN, BREAK_OUT)

# 勤務状態
STATUS_OFF = "off"            # 未出勤 / 退勤済み
STATUS_WORKING = "working"    # 勤務中
STATUS_ON_BREAK = "on_break"  # 休憩中

# 1 日の所定労働時間(分)。これを超えた分を残業とみなす。
STANDARD_WORK_MINUTES = 8 * 60


@dataclass(frozen=True)
class Punch:
    """1 件の打刻イベント。"""

    punch_type: str
    punched_at: datetime

    def __post_init__(self) -> None:
        if self.punch_type not in PUNCH_TYPES:
            raise ValueError(f"不正な打刻種別です: {self.punch_type!r}")


@dataclass
class DaySummary:
    """1 日分の勤怠集計結果。"""

    work_minutes: int = 0       # 実労働時間(休憩を除く)
    break_minutes: int = 0      # 休憩時間
    overtime_minutes: int = 0   # 残業時間(所定労働時間超過分)
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    incomplete: bool = False    # 退勤打刻が無いなど、区間が閉じていない
    warnings: list[str] = field(default_factory=list)

    @property
    def work_hours(self) -> float:
        return round(self.work_minutes / 60, 2)

    @property
    def break_hours(self) -> float:
        return round(self.break_minutes / 60, 2)

    @property
    def overtime_hours(self) -> float:
        return round(self.overtime_minutes / 60, 2)


def next_allowed_punches(status: str) -> tuple[str, ...]:
    """現在の状態から次に打刻可能な種別を返す。"""
    if status == STATUS_OFF:
        return (PUNCH_IN,)
    if status == STATUS_WORKING:
        return (PUNCH_OUT, BREAK_IN)
    if status == STATUS_ON_BREAK:
        return (BREAK_OUT,)
    raise ValueError(f"不正な状態です: {status!r}")


def compute_status(punches: list[Punch]) -> str:
    """打刻履歴から現在の勤務状態を判定する。

    末尾の打刻種別だけで状態が決まる。
    """
    if not punches:
        return STATUS_OFF
    last = punches[-1].punch_type
    if last == PUNCH_IN or last == BREAK_OUT:
        return STATUS_WORKING
    if last == BREAK_IN:
        return STATUS_ON_BREAK
    # PUNCH_OUT
    return STATUS_OFF


def validate_transition(status: str, punch_type: str) -> None:
    """状態遷移として正しい打刻かを検証する。不正なら ValueError。"""
    allowed = next_allowed_punches(status)
    if punch_type not in allowed:
        raise ValueError(
            f"現在の状態 '{status}' では '{punch_type}' の打刻はできません。"
            f"打刻可能: {allowed}"
        )


def summarize_day(punches: list[Punch]) -> DaySummary:
    """同一日の打刻リスト(時刻昇順)から勤怠を集計する。

    複数回の出退勤(中抜け)にも対応する。休憩は勤務区間内のもののみ
    労働時間から差し引く。
    """
    ordered = sorted(punches, key=lambda p: p.punched_at)
    summary = DaySummary()

    work_start: datetime | None = None
    break_start: datetime | None = None

    for punch in ordered:
        t = punch.punch_type
        at = punch.punched_at

        if t == PUNCH_IN:
            if work_start is not None:
                summary.warnings.append("出勤の打刻が連続しています。")
            else:
                work_start = at
            if summary.clock_in is None:
                summary.clock_in = at

        elif t == PUNCH_OUT:
            if work_start is None:
                summary.warnings.append("出勤打刻の無い退勤があります。")
            else:
                summary.work_minutes += _minutes_between(work_start, at)
                work_start = None
            summary.clock_out = at

        elif t == BREAK_IN:
            if break_start is not None:
                summary.warnings.append("休憩開始が連続しています。")
            else:
                break_start = at

        elif t == BREAK_OUT:
            if break_start is None:
                summary.warnings.append("休憩開始の無い休憩終了があります。")
            else:
                minutes = _minutes_between(break_start, at)
                summary.break_minutes += minutes
                # 勤務中の休憩は労働時間から差し引く
                if work_start is not None:
                    summary.work_minutes -= minutes
                break_start = None

    # 閉じていない区間の検出
    if work_start is not None:
        summary.incomplete = True
        summary.warnings.append("退勤の打刻がありません。")
    if break_start is not None:
        summary.incomplete = True
        summary.warnings.append("休憩終了の打刻がありません。")

    if summary.work_minutes < 0:
        summary.work_minutes = 0

    summary.overtime_minutes = max(0, summary.work_minutes - STANDARD_WORK_MINUTES)
    return summary


def _minutes_between(start: datetime, end: datetime) -> int:
    """2 時刻の差を分単位(切り捨て)で返す。負なら 0。"""
    delta: timedelta = end - start
    minutes = int(delta.total_seconds() // 60)
    return max(0, minutes)
