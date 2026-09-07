"""PL・BS の計算ロジック(calc)のユニットテスト。"""

import pytest

from enop_finance import calc
from enop_finance.calc import Entry


def _pl(**by_category):
    entries = [
        Entry(category=category, item=category, amount=amount)
        for category, amount in by_category.items()
    ]
    return calc.compute_pl(entries, "2026-09")


def _bs(**by_category):
    entries = [
        Entry(category=category, item=category, amount=amount)
        for category, amount in by_category.items()
    ]
    return calc.compute_bs(entries, "2026-09")


# ---- PL --------------------------------------------------------------------

def test_pl_totals():
    # 売上 240,000 / 原価 72,000 / 人件費 60,000 / その他販管費 33,000
    pl = _pl(revenue=24_000_000, cogs=7_200_000, labor=6_000_000, opex=3_300_000)
    assert pl.gross_profit == 16_800_000       # 168,000
    assert pl.operating_cost == 9_300_000      # 93,000
    assert pl.operating_income == 7_500_000    # 75,000
    assert pl.ordinary_income == 7_500_000
    assert pl.net_income == 7_500_000


def test_pl_non_operating_and_tax():
    pl = _pl(
        revenue=10_000_000,
        cogs=4_000_000,
        opex=2_000_000,
        other_income=500_000,
        other_expense=300_000,
        tax=1_000_000,
    )
    assert pl.operating_income == 4_000_000
    assert pl.ordinary_income == 4_200_000   # 営業利益 + 営業外収益 - 営業外費用
    assert pl.net_income == 3_200_000        # 経常利益 - 法人税等


def test_pl_margins():
    pl = _pl(revenue=20_000_000, cogs=8_000_000, opex=4_000_000)
    assert pl.gross_margin == 60.0
    assert pl.operating_margin == 40.0
    assert pl.net_margin == 40.0


def test_pl_margins_with_no_revenue():
    # 開店前など売上ゼロの月でもゼロ除算しない
    pl = _pl(opex=1_000_000)
    assert pl.revenue == 0
    assert pl.operating_income == -1_000_000
    assert pl.gross_margin == 0.0
    assert pl.operating_margin == 0.0


def test_pl_ignores_bs_categories():
    entries = [
        Entry(category="revenue", item="売上", amount=1_000_000),
        Entry(category="current_asset", item="現金", amount=9_000_000),
    ]
    pl = calc.compute_pl(entries)
    assert pl.revenue == 1_000_000
    assert all(section.category in calc.PL_CATEGORIES for section in pl.sections.values())


def test_pl_profit_basis():
    pl = _pl(revenue=10_000_000, opex=2_000_000, tax=1_000_000)
    assert pl.profit(calc.BASIS_OPERATING) == 8_000_000
    assert pl.profit(calc.BASIS_NET) == 7_000_000


def test_empty_pl():
    pl = calc.compute_pl([], "2026-09")
    assert pl.is_empty
    assert pl.operating_income == 0


# ---- BS --------------------------------------------------------------------

def test_bs_balanced():
    bs = _bs(
        current_asset=12_000_000,
        fixed_asset=30_000_000,
        current_liability=4_000_000,
        long_liability=20_000_000,
        equity=18_000_000,
    )
    assert bs.total_assets == 42_000_000
    assert bs.total_liabilities == 24_000_000
    assert bs.total_liabilities_and_equity == 42_000_000
    assert bs.difference == 0
    assert bs.balanced


def test_bs_unbalanced_reports_difference():
    bs = _bs(current_asset=10_000_000, equity=6_000_000)
    assert not bs.balanced
    assert bs.difference == 4_000_000


def test_bs_ratios():
    bs = _bs(
        current_asset=12_000_000,
        fixed_asset=8_000_000,
        current_liability=6_000_000,
        equity=14_000_000,
    )
    assert bs.working_capital == 6_000_000
    assert bs.current_ratio == 200.0   # 流動資産 ÷ 流動負債
    assert bs.equity_ratio == 70.0     # 純資産 ÷ 資産合計


def test_bs_ratios_without_liabilities():
    bs = _bs(current_asset=1_000_000, equity=1_000_000)
    assert bs.current_ratio == 0.0
    assert bs.equity_ratio == 100.0


# ---- 目標利益 --------------------------------------------------------------

def test_default_target_is_30k_to_50k():
    assert calc.TARGET_MIN == 3_000_000
    assert calc.TARGET_MAX == 5_000_000


def test_target_below():
    status = calc.evaluate_target(2_000_000)  # $20,000
    assert status.status == calc.STATUS_BELOW
    assert status.label == "未達"
    assert not status.achieved
    assert status.gap_to_min == 1_000_000       # $10,000 不足
    assert status.achievement_rate == 66.7


def test_target_in_range():
    status = calc.evaluate_target(4_000_000)  # $40,000
    assert status.status == calc.STATUS_IN_RANGE
    assert status.achieved
    assert status.gap_to_min == 0
    assert status.gap_to_max == 1_000_000
    assert status.surplus_over_max == 0


def test_target_boundaries_are_inclusive():
    assert calc.evaluate_target(3_000_000).status == calc.STATUS_IN_RANGE
    assert calc.evaluate_target(5_000_000).status == calc.STATUS_IN_RANGE


def test_target_above():
    status = calc.evaluate_target(6_000_000)  # $60,000
    assert status.status == calc.STATUS_ABOVE
    assert status.surplus_over_max == 1_000_000
    assert status.annual_run_rate == 72_000_000


def test_target_loss_month():
    status = calc.evaluate_target(-500_000)
    assert status.status == calc.STATUS_BELOW
    assert status.gap_to_min == 3_500_000
    assert status.progress == 0.0


def test_target_custom_range_is_normalized():
    status = calc.evaluate_target(3_500_000, target_min=5_000_000, target_max=3_000_000)
    assert status.target_min == 3_000_000
    assert status.target_max == 5_000_000
    assert status.achieved


# ---- 損益分岐点・必要売上 --------------------------------------------------

def test_breakeven_revenue():
    # 変動費率 30%、固定費 $70,000 → 損益分岐点 $100,000
    pl = _pl(revenue=10_000_000, cogs=3_000_000, labor=4_000_000, opex=3_000_000)
    assert calc.variable_cost_ratio(pl) == 0.3
    assert calc.fixed_cost(pl) == 7_000_000
    assert calc.breakeven_revenue(pl) == 10_000_000


def test_revenue_needed_for_target():
    # 固定費 $70,000・変動費率 30% で $30,000 の利益を出すには売上 $142,857.14
    pl = _pl(revenue=10_000_000, cogs=3_000_000, labor=4_000_000, opex=3_000_000)
    assert calc.revenue_needed_for_target(pl, calc.TARGET_MIN) == 14_285_714


def test_required_revenue_unavailable_when_cost_exceeds_sales():
    # 原価率 100% 以上では必要売上を算出できない
    assert calc.required_revenue(1_000_000, 1.0, 3_000_000) is None
    assert calc.required_revenue(1_000_000, 1.4, 3_000_000) is None


def test_breakeven_without_revenue_returns_fixed_cost():
    pl = _pl(opex=2_500_000)
    assert calc.breakeven_revenue(pl) == 2_500_000


# ---- 金額・月のユーティリティ ---------------------------------------------

@pytest.mark.parametrize(
    "raw,cents",
    [("1234.56", 123_456), ("1,234.56", 123_456), ("$30,000", 3_000_000),
     (1234.5, 123_450), ("-500", -50_000), ("0.005", 1)],
)
def test_parse_amount(raw, cents):
    assert calc.parse_amount(raw) == cents


@pytest.mark.parametrize("raw", ["", "   ", None, "abc"])
def test_parse_amount_rejects_invalid(raw):
    with pytest.raises(ValueError):
        calc.parse_amount(raw)


def test_format_usd():
    assert calc.format_usd(123_456) == "$1,234.56"
    assert calc.format_usd(-123_456) == "-$1,234.56"
    assert calc.format_usd(0) == "$0.00"


def test_month_shift():
    assert calc.month_shift("2026-09", 1) == "2026-10"
    assert calc.month_shift("2026-01", -1) == "2025-12"
    assert calc.month_shift("2026-12", 2) == "2027-02"


def test_is_valid_month():
    assert calc.is_valid_month("2026-09")
    assert not calc.is_valid_month("2026-13")
    assert not calc.is_valid_month("2026-9")
    assert not calc.is_valid_month("")


def test_validate_category():
    assert calc.validate_category("revenue") == "revenue"
    assert calc.validate_category("equity", "bs") == "equity"
    with pytest.raises(ValueError):
        calc.validate_category("unknown")
    with pytest.raises(ValueError):
        calc.validate_category("revenue", "bs")


def test_yen_to_cents():
    # 1,500,000 円 ÷ 150 円/$ = $10,000
    assert calc.yen_to_cents(1_500_000, 150) == 1_000_000
    with pytest.raises(ValueError):
        calc.yen_to_cents(1000, 0)


def test_entry_statement_and_source():
    manual = Entry(category="revenue", item="売上", amount=100)
    imported = Entry(category="labor", item="給与", amount=100, source=calc.SOURCE_IMPORT)
    assert manual.statement == "pl"
    assert not manual.imported
    assert Entry(category="equity", item="資本金", amount=100).statement == "bs"
    assert imported.imported
