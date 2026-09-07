"""給与計算のドメインロジック(純粋関数)。

勤怠集計(attendance.DaySummary)と時給から月次の支給額を算出する。
金額は香港ドル(HK$)。データベースや Web に依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .attendance import DaySummary

# 残業割増率(法定 25% 増しを既定とする)
DEFAULT_OVERTIME_RATE = 1.25


@dataclass
class MonthlyPay:
    """1 社員・1 か月分の給与計算結果。"""

    work_days: int = 0            # 出勤日数
    work_minutes: int = 0         # 実労働時間(合計)
    overtime_minutes: int = 0     # 残業時間(合計)
    regular_minutes: int = 0      # 通常労働時間(実労働 - 残業)
    hourly_wage: int = 0          # 時給(HK$)
    overtime_rate: float = DEFAULT_OVERTIME_RATE
    base_pay: int = 0             # 基本給(通常時間分)
    overtime_pay: int = 0         # 残業手当(割増込み)
    total_pay: int = 0            # 支給額合計
    has_incomplete: bool = False  # 打刻漏れを含む日があるか

    @property
    def work_hours(self) -> float:
        return round(self.work_minutes / 60, 2)

    @property
    def overtime_hours(self) -> float:
        return round(self.overtime_minutes / 60, 2)

    @property
    def regular_hours(self) -> float:
        return round(self.regular_minutes / 60, 2)


def compute_monthly_pay(
    summaries: list[DaySummary],
    hourly_wage: int,
    overtime_rate: float = DEFAULT_OVERTIME_RATE,
) -> MonthlyPay:
    """日別集計のリストと時給から月次給与を計算する。

    - 通常時間分 = (実労働 - 残業) を時給で支給
    - 残業時間分 = 残業を時給 × 割増率 で支給
    金額は HK$1 未満を四捨五入して整数化する。
    """
    pay = MonthlyPay(hourly_wage=hourly_wage, overtime_rate=overtime_rate)

    for summary in summaries:
        # 実労働が 0 の日(打刻はあるが労働時間が無い)は出勤日に数えない
        if summary.work_minutes > 0:
            pay.work_days += 1
        pay.work_minutes += summary.work_minutes
        pay.overtime_minutes += summary.overtime_minutes
        if summary.incomplete:
            pay.has_incomplete = True

    pay.regular_minutes = pay.work_minutes - pay.overtime_minutes

    wage = Decimal(hourly_wage)
    base = wage * Decimal(pay.regular_minutes) / Decimal(60)
    overtime = wage * Decimal(str(overtime_rate)) * Decimal(pay.overtime_minutes) / Decimal(60)

    pay.base_pay = _to_dollars(base)
    pay.overtime_pay = _to_dollars(overtime)
    pay.total_pay = pay.base_pay + pay.overtime_pay
    return pay


def _to_dollars(amount: Decimal) -> int:
    """HK$1 未満を四捨五入して整数の HK$ に変換する。"""
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
