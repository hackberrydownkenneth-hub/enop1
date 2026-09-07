"""累計損益・投資回収・将来予測のユニットテスト。"""

import pytest

from enop_finance import lifecycle
from enop_finance.lifecycle import MonthResult

# $ を セントに
def _m(month, revenue, profit, net=None):
    return MonthResult(
        month=month,
        revenue=revenue * 100,
        profit=profit * 100,
        net_income=(net if net is not None else profit) * 100,
    )


# 開店 → 赤字 2 か月 → 黒字化
HISTORY = [
    _m("2026-04", 118_000, -15_000),
    _m("2026-05", 152_000, 8_000),
    _m("2026-06", 181_000, 28_000),
    _m("2026-07", 205_000, 44_000),
]
INVESTMENT = 360_000 * 100


# ---- 累計 ------------------------------------------------------------------

def test_build_history_accumulates_profit():
    points = lifecycle.build_history(HISTORY, INVESTMENT)
    assert [p.cumulative_profit for p in points] == [
        -1_500_000, -700_000, 2_100_000, 6_500_000
    ]
    # 通算損益は初期投資からのスタート
    assert points[0].position == -37_500_000
    assert points[-1].position == -29_500_000
    assert points[-1].remaining == 29_500_000
    assert points[-1].recovery_rate == 18.1


def test_history_without_investment():
    points = lifecycle.build_history(HISTORY, 0)
    assert points[-1].position == points[-1].cumulative_profit
    assert points[-1].recovery_rate == 0.0
    assert points[-1].remaining == 0


# ---- 回収状況 --------------------------------------------------------------

def test_payback_in_progress():
    payback = lifecycle.evaluate_payback(HISTORY, INVESTMENT)
    assert payback.months_elapsed == 4
    assert payback.profitable_months == 3
    assert payback.first_profitable_month == "2026-05"
    assert payback.cumulative_profit == 6_500_000
    assert payback.position == -29_500_000
    assert not payback.recovered
    assert payback.remaining == 29_500_000
    assert payback.payback_month is None
    assert payback.phase == lifecycle.PHASE_EARNING


def test_payback_tracks_the_bottom():
    payback = lifecycle.evaluate_payback(HISTORY, INVESTMENT)
    # 最も沈んだのは開店初月(投資 + 初月赤字)
    assert payback.worst_month == "2026-04"
    assert payback.worst_position == -37_500_000


def test_payback_completed():
    months = HISTORY + [_m("2026-08", 300_000, 300_000)]
    payback = lifecycle.evaluate_payback(months, INVESTMENT)
    assert payback.recovered
    assert payback.payback_month == "2026-08"
    assert payback.remaining == 0
    assert payback.surplus == 6_500_000 + 30_000_000 - 36_000_000
    assert payback.phase == lifecycle.PHASE_RECOVERED


def test_payback_before_opening():
    payback = lifecycle.evaluate_payback([], INVESTMENT)
    assert payback.months_elapsed == 0
    assert payback.phase == lifecycle.PHASE_PRE_OPEN
    assert payback.remaining == INVESTMENT
    assert payback.recovery_rate == 0.0


def test_payback_while_still_losing_money():
    months = [_m("2026-04", 50_000, -20_000), _m("2026-05", 60_000, -10_000)]
    payback = lifecycle.evaluate_payback(months, INVESTMENT)
    assert payback.phase == lifecycle.PHASE_INVESTING
    assert payback.first_profitable_month is None
    assert payback.recent_average_profit == -1_500_000


def test_payback_averages_use_the_recent_window():
    payback = lifecycle.evaluate_payback(HISTORY, INVESTMENT, recent_months=2)
    assert payback.recent_months == 2
    assert payback.recent_average_profit == 3_600_000   # (28,000 + 44,000) / 2
    assert payback.average_profit == 1_625_000          # 開店からの平均


def test_empty_months_are_ignored():
    months = [_m("2026-01", 0, 0), _m("2026-02", 0, 0)] + HISTORY
    payback = lifecycle.evaluate_payback(months, INVESTMENT)
    assert payback.months_elapsed == 4


# ---- 予測 ------------------------------------------------------------------

def test_forecast_scenarios():
    payback = lifecycle.evaluate_payback(HISTORY, INVESTMENT)
    scenarios = lifecycle.forecast_scenarios(payback, 3_000_000, 5_000_000)
    by_key = {s.key: s for s in scenarios}

    # 残り $295,000 を月 $30,000 で → 10 か月
    assert by_key["target_min"].months_needed == 10
    assert by_key["target_min"].finish_month == "2027-05"
    # 月 $50,000 なら 6 か月
    assert by_key["target_max"].months_needed == 6
    assert by_key["target_max"].finish_month == "2027-01"
    # 直近 3 か月平均($26,666.67)なら 12 か月
    assert by_key["recent"].months_needed == 12


def test_forecast_impossible_when_losing_money():
    months = [_m("2026-04", 50_000, -20_000)]
    payback = lifecycle.evaluate_payback(months, INVESTMENT)
    recent = [s for s in lifecycle.forecast_scenarios(payback, 3_000_000, 5_000_000)
              if s.key == "recent"][0]
    assert recent.months_needed is None
    assert recent.finish_month is None
    assert not recent.possible


def test_forecast_is_zero_when_already_recovered():
    months = HISTORY + [_m("2026-08", 400_000, 400_000)]
    payback = lifecycle.evaluate_payback(months, INVESTMENT)
    scenario = lifecycle.forecast_scenarios(payback, 3_000_000, 5_000_000)[0]
    assert scenario.months_needed == 0
    assert scenario.finish_month == "2026-08"


def test_project_extends_the_position():
    payback = lifecycle.evaluate_payback(HISTORY, INVESTMENT)
    points = lifecycle.project(payback, 3_000_000, 3)
    assert [p.month for p in points] == ["2026-08", "2026-09", "2026-10"]
    assert all(p.forecast for p in points)
    assert points[0].position == -29_500_000 + 3_000_000
    assert points[-1].position == -29_500_000 + 9_000_000


def test_project_without_history():
    payback = lifecycle.evaluate_payback([], INVESTMENT)
    assert lifecycle.project(payback, 3_000_000, 3) == []


@pytest.mark.parametrize(
    "amount,profit,expected",
    [(0, 1_000, 0), (10_000, 1_000, 10), (10_001, 1_000, 11), (10_000, 0, None),
     (10_000, -500, None)],
)
def test_months_to_cover(amount, profit, expected):
    assert lifecycle.months_to_cover(amount, profit) == expected


# ---- 投資余力・次にやれること ----------------------------------------------

def test_investment_capacity():
    capacity = lifecycle.investment_capacity(
        cash=20_000_000, monthly_fixed_cost=3_000_000, reserve_months=3
    )
    assert capacity.reserve_needed == 9_000_000
    assert capacity.available == 11_000_000


def test_investment_capacity_never_negative():
    capacity = lifecycle.investment_capacity(1_000_000, 3_000_000, 3)
    assert capacity.available == 0


def test_plan_ready_now():
    capacity = lifecycle.investment_capacity(20_000_000, 1_000_000, 3)
    plans = lifecycle.evaluate_plans(
        [(1, "厨房設備の更新", 4_000_000, "")], capacity, 3_000_000, "2026-07"
    )
    plan = plans[0]
    assert plan.funded
    assert plan.shortfall == 0
    assert plan.months_needed == 0
    assert plan.progress == 100.0


def test_plan_needs_more_months():
    capacity = lifecycle.investment_capacity(10_000_000, 2_000_000, 3)   # 余力 $40,000
    plans = lifecycle.evaluate_plans(
        [(1, "2 号店の出店", 30_000_000, "")], capacity, 3_000_000, "2026-07"
    )
    plan = plans[0]
    assert not plan.funded
    assert plan.shortfall == 26_000_000
    assert plan.months_needed == 9          # $260,000 ÷ $30,000 → 切り上げ
    assert plan.ready_month == "2027-04"
    assert plan.progress == 13.3


def test_plan_unreachable_without_profit():
    capacity = lifecycle.investment_capacity(1_000_000, 2_000_000, 3)
    plans = lifecycle.evaluate_plans(
        [(1, "2 号店の出店", 30_000_000, "")], capacity, -500_000, "2026-07"
    )
    assert plans[0].months_needed is None
    assert plans[0].ready_month is None
