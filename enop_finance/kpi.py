"""経営指標(KPI)のドメインロジック(純粋関数)。

PL・BS の計算結果(calc.py)と手入力の月次データ(客数・営業日数・現金残高)から、
毎月ウォッチする指標を組み立てる。金額はセント、比率はパーセントで扱う。
データベースや Web フレームワークには依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from . import calc
from .calc import BalanceSheet, ProfitLoss, TargetStatus

# FL 比率(原価率 + 人件費率)の判定しきい値(%)。飲食では 60% 以下が目安。
FL_GOOD = 60.0
FL_WARN = 65.0

# 指標の評価
LEVEL_GOOD = "good"    # 良好
LEVEL_WARN = "warn"    # 注意
LEVEL_BAD = "bad"      # 要改善
LEVEL_NONE = "none"    # データ不足で判定できない
LEVEL_LABELS = {
    LEVEL_GOOD: "良好",
    LEVEL_WARN: "注意",
    LEVEL_BAD: "要改善",
    LEVEL_NONE: "データなし",
}

# 現金残高を BS から推定するときに現金とみなす科目名
CASH_KEYWORDS = ("現金", "預金", "キャッシュ", "cash", "bank")


@dataclass
class MonthlyInputs:
    """月次の手入力データ(PL・BS には出てこない指標)。"""

    customers: int = 0            # 客数(組数ではなく人数)
    open_days: int = 0            # 営業日数
    cash_balance: int | None = None  # 現金残高(セント)。None なら BS から推定

    @property
    def has_customers(self) -> bool:
        return self.customers > 0

    @property
    def has_open_days(self) -> bool:
        return self.open_days > 0


@dataclass
class Kpi:
    """1 か月分の経営指標。"""

    month: str
    pl: ProfitLoss
    bs: BalanceSheet
    target: TargetStatus
    inputs: MonthlyInputs

    # ---- 売上・客数・客単価 ----

    @property
    def revenue(self) -> int:
        return self.pl.revenue

    @property
    def customers(self) -> int:
        return self.inputs.customers

    @property
    def average_spend(self) -> int | None:
        """客単価(売上 ÷ 客数)。客数未入力なら None。"""
        if not self.inputs.has_customers:
            return None
        return _round_cents(Decimal(self.revenue) / self.inputs.customers)

    @property
    def daily_sales(self) -> int | None:
        """日商(売上 ÷ 営業日数)。営業日数未入力なら None。"""
        if not self.inputs.has_open_days:
            return None
        return _round_cents(Decimal(self.revenue) / self.inputs.open_days)

    @property
    def daily_customers(self) -> float | None:
        """1 日あたり客数。"""
        if not (self.inputs.has_customers and self.inputs.has_open_days):
            return None
        return round(self.customers / self.inputs.open_days, 1)

    # ---- 原価率・人件費率(FL 比率) ----

    @property
    def food_ratio(self) -> float:
        """原価率 F(売上原価 ÷ 売上高)。"""
        return _percent(self.pl.cogs, self.revenue)

    @property
    def labor_ratio(self) -> float:
        """人件費率 L(人件費 ÷ 売上高)。"""
        return _percent(self.pl.labor_cost, self.revenue)

    @property
    def fl_ratio(self) -> float:
        """FL 比率(原価 + 人件費)÷ 売上高。"""
        return _percent(self.pl.cogs + self.pl.labor_cost, self.revenue)

    @property
    def fl_level(self) -> str:
        return fl_level(self.fl_ratio, has_revenue=self.revenue > 0)

    @property
    def rent_ratio(self) -> float:
        """その他販管費率(家賃を含む)。"""
        return _percent(self.pl.opex, self.revenue)

    # ---- 現金・損益分岐点・ランウェイ ----

    @property
    def cash(self) -> int:
        return cash_balance(self.bs, self.inputs.cash_balance)

    @property
    def cash_is_estimated(self) -> bool:
        """現金残高を BS から推定しているか(手入力があれば False)。"""
        return self.inputs.cash_balance is None

    @property
    def monthly_burn(self) -> int:
        """月次の営業赤字額。黒字なら 0。"""
        return max(0, -self.pl.operating_income)

    @property
    def runway_months(self) -> float | None:
        """現金が尽きるまでの月数。黒字または現金不明なら None。"""
        return runway(self.cash, self.monthly_burn)

    @property
    def breakeven_revenue(self) -> int | None:
        return calc.breakeven_revenue(self.pl)

    @property
    def needed_revenue(self) -> int | None:
        """目標下限を達成するために必要な売上。"""
        return calc.revenue_needed_for_target(self.pl, self.target.target_min)

    @property
    def needed_daily_sales(self) -> int | None:
        """目標達成に必要な日商。"""
        needed = self.needed_revenue
        if needed is None or not self.inputs.has_open_days:
            return None
        return _round_cents(Decimal(needed) / self.inputs.open_days)

    @property
    def needed_customers(self) -> int | None:
        """今の客単価で目標を達成するのに必要な客数。"""
        needed, spend = self.needed_revenue, self.average_spend
        if needed is None or not spend:
            return None
        return -(-needed // spend)  # 切り上げ

    @property
    def revenue_gap(self) -> int:
        """目標達成に必要な売上と実績売上の差。達成済みなら 0。"""
        needed = self.needed_revenue
        if needed is None:
            return 0
        return max(0, needed - self.revenue)


@dataclass
class TrendPoint:
    """月次推移の 1 点。"""

    month: str
    revenue: int
    operating_income: int
    net_income: int
    fl_ratio: float
    target_min: int
    achieved: bool


def build_kpi(
    month: str,
    pl: ProfitLoss,
    bs: BalanceSheet,
    target: TargetStatus,
    inputs: MonthlyInputs | None = None,
) -> Kpi:
    """PL・BS・目標・手入力データから月次 KPI を組み立てる。"""
    return Kpi(month=month, pl=pl, bs=bs, target=target, inputs=inputs or MonthlyInputs())


def fl_level(ratio: float, has_revenue: bool = True) -> str:
    """FL 比率を 良好 / 注意 / 要改善 で評価する。"""
    if not has_revenue:
        return LEVEL_NONE
    if ratio <= FL_GOOD:
        return LEVEL_GOOD
    if ratio <= FL_WARN:
        return LEVEL_WARN
    return LEVEL_BAD


def cash_balance(bs: BalanceSheet, override: int | None = None) -> int:
    """現金残高。手入力があればそれを、無ければ BS の流動資産から推定する。"""
    if override is not None:
        return override
    section = bs.sections.get("current_asset")
    if section is None:
        return 0
    return sum(line.amount for line in section.lines if _looks_like_cash(line.item))


def runway(cash: int, burn: int) -> float | None:
    """現金がいまの赤字ペースで何か月もつか。黒字(burn=0)なら None。"""
    if burn <= 0 or cash <= 0:
        return None
    return round(cash / burn, 1)


def build_trend(months: list[tuple[str, ProfitLoss, TargetStatus]]) -> list[TrendPoint]:
    """月次推移(古い月 → 新しい月)を組み立てる。"""
    points = []
    for month, pl, target in months:
        points.append(
            TrendPoint(
                month=month,
                revenue=pl.revenue,
                operating_income=pl.operating_income,
                net_income=pl.net_income,
                fl_ratio=_percent(pl.cogs + pl.labor_cost, pl.revenue),
                target_min=target.target_min,
                achieved=target.achieved,
            )
        )
    return points


def trend_summary(points: list[TrendPoint]) -> dict[str, object]:
    """推移から達成月数や平均利益などのサマリを作る。"""
    active = [p for p in points if p.revenue or p.operating_income]
    if not active:
        return {"months": 0, "achieved_months": 0, "average_profit": 0, "best_month": None}
    achieved = [p for p in active if p.achieved]
    best = max(active, key=lambda p: p.operating_income)
    return {
        "months": len(active),
        "achieved_months": len(achieved),
        "average_profit": _round_cents(
            Decimal(sum(p.operating_income for p in active)) / len(active)
        ),
        "best_month": best.month,
    }


# ---- 内部ヘルパー ----------------------------------------------------------

def _looks_like_cash(item: str) -> bool:
    lowered = item.lower()
    return any(keyword.lower() in lowered for keyword in CASH_KEYWORDS)


def _percent(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _round_cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
