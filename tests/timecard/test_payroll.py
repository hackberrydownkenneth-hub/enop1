"""給与計算ロジックのユニットテスト。"""

from datetime import datetime

from timecard import attendance, payroll
from timecard.attendance import Punch


def _day(in_h, out_h):
    return attendance.summarize_day(
        [
            Punch("in", datetime(2026, 8, 10, in_h, 0)),
            Punch("out", datetime(2026, 8, 10, out_h, 0)),
        ]
    )


def test_base_pay_no_overtime():
    # 8 時間勤務・時給 HK$1,000 → HK$8,000、残業なし
    pay = payroll.compute_monthly_pay([_day(9, 17)], hourly_wage=1000)
    assert pay.work_days == 1
    assert pay.work_minutes == 8 * 60
    assert pay.overtime_minutes == 0
    assert pay.base_pay == 8000
    assert pay.overtime_pay == 0
    assert pay.total_pay == 8000


def test_overtime_premium():
    # 10 時間勤務・時給 HK$1,000 → 基本 8,000 + 残業 2h×1,000×1.25=2,500 = 10,500
    pay = payroll.compute_monthly_pay([_day(9, 19)], hourly_wage=1000)
    assert pay.overtime_minutes == 2 * 60
    assert pay.base_pay == 8000
    assert pay.overtime_pay == 2500
    assert pay.total_pay == 10500


def test_multiple_days_accumulate():
    pay = payroll.compute_monthly_pay([_day(9, 17), _day(9, 17)], hourly_wage=1200)
    assert pay.work_days == 2
    assert pay.total_pay == 8 * 1200 * 2


def test_custom_overtime_rate():
    pay = payroll.compute_monthly_pay([_day(9, 19)], hourly_wage=1000, overtime_rate=1.5)
    # 残業 2h × 1000 × 1.5 = 3000
    assert pay.overtime_pay == 3000


def test_zero_wage():
    pay = payroll.compute_monthly_pay([_day(9, 19)], hourly_wage=0)
    assert pay.total_pay == 0


def test_incomplete_flag():
    incomplete = attendance.summarize_day([Punch("in", datetime(2026, 8, 10, 9, 0))])
    pay = payroll.compute_monthly_pay([incomplete], hourly_wage=1000)
    assert pay.has_incomplete
