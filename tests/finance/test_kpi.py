"""経営指標(KPI)のユニットテスト。"""

import pytest

from enop_finance import calc, kpi
from enop_finance.calc import Entry


def _statements(**by_category):
    """カテゴリ→金額(ドル)から PL・BS を組み立てる。"""
    entries = [
        Entry(category=category, item=category, amount=dollars * 100)
        for category, dollars in by_category.items()
    ]
    pl = calc.compute_pl(entries, "2026-09")
    bs = calc.compute_bs(entries, "2026-09")
    target = calc.evaluate_target(pl.operating_income)
    return pl, bs, target


def _kpi(customers=0, open_days=0, cash=None, **by_category):
    pl, bs, target = _statements(**by_category)
    inputs = kpi.MonthlyInputs(customers=customers, open_days=open_days, cash_balance=cash)
    return kpi.build_kpi("2026-09", pl, bs, target, inputs)


# ---- 売上・客数・客単価 ----------------------------------------------------

def test_average_spend_and_daily_sales():
    metrics = _kpi(customers=4_000, open_days=25, revenue=200_000)
    assert metrics.average_spend == 5_000        # $50.00
    assert metrics.daily_sales == 800_000        # $8,000.00
    assert metrics.daily_customers == 160.0


def test_sales_metrics_without_inputs():
    metrics = _kpi(revenue=200_000)
    assert metrics.average_spend is None
    assert metrics.daily_sales is None
    assert metrics.daily_customers is None


def test_average_spend_rounds_to_cents():
    metrics = _kpi(customers=3, revenue=100)
    assert metrics.average_spend == 3_333        # $33.33


# ---- FL 比率 ---------------------------------------------------------------

def test_fl_ratio():
    metrics = _kpi(revenue=200_000, cogs=60_000, labor=50_000, opex=30_000)
    assert metrics.food_ratio == 30.0
    assert metrics.labor_ratio == 25.0
    assert metrics.fl_ratio == 55.0
    assert metrics.rent_ratio == 15.0
    assert metrics.fl_level == kpi.LEVEL_GOOD


@pytest.mark.parametrize(
    "cogs,labor,level",
    [
        (60_000, 60_000, kpi.LEVEL_GOOD),   # 60% ちょうどは良好
        (65_000, 60_000, kpi.LEVEL_WARN),   # 62.5% は注意
        (80_000, 60_000, kpi.LEVEL_BAD),    # 70% は要改善
    ],
)
def test_fl_level_thresholds(cogs, labor, level):
    metrics = _kpi(revenue=200_000, cogs=cogs, labor=labor)
    assert metrics.fl_level == level


def test_fl_level_without_revenue():
    metrics = _kpi(labor=20_000)
    assert metrics.fl_ratio == 0.0
    assert metrics.fl_level == kpi.LEVEL_NONE


# ---- 現金・ランウェイ ------------------------------------------------------

def test_cash_estimated_from_balance_sheet():
    pl, bs, target = _statements()
    bs.sections["current_asset"].lines.extend(
        [
            Entry(category="current_asset", item="現金預金", amount=12_000_000),
            Entry(category="current_asset", item="売掛金", amount=3_000_000),
        ]
    )
    metrics = kpi.build_kpi("2026-09", pl, bs, target)
    assert metrics.cash == 12_000_000    # 売掛金は現金に含めない
    assert metrics.cash_is_estimated


def test_manual_cash_overrides_estimate():
    metrics = _kpi(cash=5_000_000, current_asset=200_000)
    assert metrics.cash == 5_000_000
    assert not metrics.cash_is_estimated


def test_runway_when_burning_cash():
    # 現金 $60,000・月次赤字 $20,000 → 3.0 か月
    metrics = _kpi(cash=6_000_000, revenue=10_000, opex=30_000)
    assert metrics.monthly_burn == 2_000_000
    assert metrics.runway_months == 3.0


def test_no_runway_when_profitable():
    metrics = _kpi(cash=6_000_000, revenue=200_000, opex=30_000)
    assert metrics.monthly_burn == 0
    assert metrics.runway_months is None


def test_runway_without_cash():
    assert kpi.runway(0, 100_000) is None


# ---- 目標達成に必要な水準 --------------------------------------------------

def test_needed_revenue_and_gap():
    # 固定費 $70,000・変動費率 30% → 目標 $30,000 に必要な売上 $142,857.14
    metrics = _kpi(revenue=100_000, cogs=30_000, labor=40_000, opex=30_000)
    assert metrics.needed_revenue == 14_285_714
    assert metrics.revenue_gap == 4_285_714      # 実績 $100,000 との差


def test_needed_daily_sales_and_customers():
    metrics = _kpi(
        customers=2_000, open_days=25,
        revenue=100_000, cogs=30_000, labor=40_000, opex=30_000,
    )
    assert metrics.needed_daily_sales == 571_429      # $5,714.29
    # 客単価 $50 で $142,857.14 を売るには 2,858 人(切り上げ)
    assert metrics.needed_customers == 2_858


def test_no_gap_when_target_met():
    metrics = _kpi(revenue=200_000, cogs=60_000, labor=50_000, opex=30_000)
    assert metrics.target.achieved
    assert metrics.revenue_gap == 0


# ---- 推移 ------------------------------------------------------------------

def _trend_rows(*profits):
    rows = []
    for index, profit in enumerate(profits, start=1):
        pl, _bs, _target = _statements(revenue=200_000, opex=200_000 - profit)
        rows.append((f"2026-{index:02d}", pl, calc.evaluate_target(pl.operating_income)))
    return rows


def test_build_trend_and_summary():
    points = kpi.build_trend(_trend_rows(10_000, 40_000, 60_000))
    assert [p.month for p in points] == ["2026-01", "2026-02", "2026-03"]
    assert [p.achieved for p in points] == [False, True, True]

    summary = kpi.trend_summary(points)
    assert summary["months"] == 3
    assert summary["achieved_months"] == 2
    assert summary["average_profit"] == 3_666_667    # 平均 $36,666.67
    assert summary["best_month"] == "2026-03"


def test_trend_summary_ignores_empty_months():
    points = kpi.build_trend(_trend_rows(40_000)) + kpi.build_trend([])
    summary = kpi.trend_summary(points)
    assert summary["months"] == 1


def test_trend_summary_without_data():
    summary = kpi.trend_summary([])
    assert summary == {
        "months": 0, "achieved_months": 0, "average_profit": 0, "best_month": None
    }
