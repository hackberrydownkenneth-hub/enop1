"""勤怠計算ロジックのユニットテスト。"""

from datetime import datetime

import pytest

from timecard import attendance
from timecard.attendance import Punch


def _p(punch_type: str, hh: int, mm: int) -> Punch:
    return Punch(punch_type=punch_type, punched_at=datetime(2026, 8, 10, hh, mm))


def test_empty_status_is_off():
    assert attendance.compute_status([]) == attendance.STATUS_OFF


def test_status_after_each_punch():
    assert attendance.compute_status([_p("in", 9, 0)]) == attendance.STATUS_WORKING
    assert attendance.compute_status([_p("in", 9, 0), _p("break_in", 12, 0)]) == attendance.STATUS_ON_BREAK
    assert attendance.compute_status(
        [_p("in", 9, 0), _p("break_in", 12, 0), _p("break_out", 13, 0)]
    ) == attendance.STATUS_WORKING
    assert attendance.compute_status(
        [_p("in", 9, 0), _p("out", 18, 0)]
    ) == attendance.STATUS_OFF


def test_next_allowed_punches():
    assert attendance.next_allowed_punches(attendance.STATUS_OFF) == ("in",)
    assert set(attendance.next_allowed_punches(attendance.STATUS_WORKING)) == {"out", "break_in"}
    assert attendance.next_allowed_punches(attendance.STATUS_ON_BREAK) == ("break_out",)


def test_validate_transition_rejects_invalid():
    with pytest.raises(ValueError):
        attendance.validate_transition(attendance.STATUS_OFF, "out")
    with pytest.raises(ValueError):
        attendance.validate_transition(attendance.STATUS_WORKING, "in")
    # 正常系は例外を投げない
    attendance.validate_transition(attendance.STATUS_OFF, "in")


def test_invalid_punch_type_raises():
    with pytest.raises(ValueError):
        Punch(punch_type="lunch", punched_at=datetime(2026, 8, 10, 9, 0))


def test_summarize_simple_day():
    # 9:00 出勤, 18:00 退勤 → 実働 9 時間, 残業 1 時間
    summary = attendance.summarize_day([_p("in", 9, 0), _p("out", 18, 0)])
    assert summary.work_minutes == 9 * 60
    assert summary.break_minutes == 0
    assert summary.overtime_minutes == 60
    assert summary.clock_in == datetime(2026, 8, 10, 9, 0)
    assert summary.clock_out == datetime(2026, 8, 10, 18, 0)
    assert not summary.incomplete


def test_summarize_with_break():
    # 9:00-18:00 のうち 12:00-13:00 休憩 → 実働 8 時間, 休憩 1 時間, 残業なし
    summary = attendance.summarize_day(
        [_p("in", 9, 0), _p("break_in", 12, 0), _p("break_out", 13, 0), _p("out", 18, 0)]
    )
    assert summary.work_minutes == 8 * 60
    assert summary.break_minutes == 60
    assert summary.overtime_minutes == 0


def test_summarize_multiple_sessions():
    # 中抜け: 9:00-12:00 と 13:00-17:00 → 実働 7 時間
    summary = attendance.summarize_day(
        [_p("in", 9, 0), _p("out", 12, 0), _p("in", 13, 0), _p("out", 17, 0)]
    )
    assert summary.work_minutes == 7 * 60
    assert summary.overtime_minutes == 0


def test_summarize_incomplete_when_no_clock_out():
    summary = attendance.summarize_day([_p("in", 9, 0)])
    assert summary.incomplete
    assert any("退勤" in w for w in summary.warnings)


def test_summarize_handles_unordered_input():
    # 入力が時刻順でなくても内部でソートされる
    summary = attendance.summarize_day([_p("out", 18, 0), _p("in", 9, 0)])
    assert summary.work_minutes == 9 * 60


def test_summarize_break_without_start_warns():
    summary = attendance.summarize_day(
        [_p("in", 9, 0), _p("break_out", 13, 0), _p("out", 18, 0)]
    )
    assert any("休憩開始の無い" in w for w in summary.warnings)
