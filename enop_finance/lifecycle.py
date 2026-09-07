"""開店からの累計損益・投資回収・今後の予測(純粋関数)。

「オープンからいくら損して、いくら儲かって、初期投資がいつ回収できて、
これから何ができるか」を 1 か所で計算する。金額はセント。
データベースや Web フレームワークには依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .calc import month_shift

# 予測に使う直近実績の月数
RECENT_MONTHS = 3
# 手元に残しておく運転資金の月数(投資余力の計算に使う)
DEFAULT_RESERVE_MONTHS = 3

# 回収フェーズ
PHASE_PRE_OPEN = "pre_open"    # 開店前(実績なし)
PHASE_INVESTING = "investing"  # 単月赤字。投資を先行して回収中
PHASE_EARNING = "earning"      # 単月黒字。初期投資を回収中
PHASE_RECOVERED = "recovered"  # 初期投資を回収済み
PHASE_LABELS = {
    PHASE_PRE_OPEN: "開店前",
    PHASE_INVESTING: "先行投資中(単月赤字)",
    PHASE_EARNING: "回収中(単月黒字)",
    PHASE_RECOVERED: "投資回収済み",
}


@dataclass
class MonthResult:
    """1 か月の実績(累計計算の入力)。"""

    month: str
    revenue: int = 0
    profit: int = 0       # 基準利益(既定は営業利益)
    net_income: int = 0

    @property
    def has_activity(self) -> bool:
        return bool(self.revenue or self.profit or self.net_income)


@dataclass
class CumulativePoint:
    """累計推移の 1 点。"""

    month: str
    revenue: int
    profit: int
    net_income: int
    cumulative_profit: int    # 開店からの累計利益
    position: int             # 初期投資を含む通算損益(マイナス = まだ回収前)
    remaining: int            # 回収まであといくら
    recovery_rate: float      # 回収率(%)
    forecast: bool = False    # 予測値か

    @property
    def profitable(self) -> bool:
        return self.profit > 0

    @property
    def recovered(self) -> bool:
        return self.position >= 0


@dataclass
class Payback:
    """初期投資の回収状況。"""

    investment: int = 0
    cumulative_profit: int = 0
    cumulative_net_income: int = 0
    months_elapsed: int = 0
    profitable_months: int = 0
    first_profitable_month: str | None = None   # 単月で初めて黒字になった月
    payback_month: str | None = None            # 累計で投資を回収し切った月
    worst_position: int = 0                     # 通算損益が最も沈んだ額
    worst_month: str | None = None
    recent_average_profit: int = 0              # 直近数か月の平均利益
    recent_months: int = 0
    last_month: str | None = None

    @property
    def position(self) -> int:
        """通算損益(累計利益 - 初期投資)。"""
        return self.cumulative_profit - self.investment

    @property
    def recovered(self) -> bool:
        return self.investment > 0 and self.position >= 0

    @property
    def remaining(self) -> int:
        """回収まであといくら。回収済みなら 0。"""
        return max(0, self.investment - self.cumulative_profit)

    @property
    def recovery_rate(self) -> float:
        """回収率(%)。初期投資が未登録なら 0.0。"""
        if self.investment <= 0:
            return 0.0
        return round(max(0, self.cumulative_profit) / self.investment * 100, 1)

    @property
    def surplus(self) -> int:
        """回収後に積み上がった利益。回収前は 0。"""
        return max(0, self.position)

    @property
    def phase(self) -> str:
        if self.months_elapsed == 0:
            return PHASE_PRE_OPEN
        if self.recovered:
            return PHASE_RECOVERED
        if self.recent_average_profit > 0:
            return PHASE_EARNING
        return PHASE_INVESTING

    @property
    def phase_label(self) -> str:
        return PHASE_LABELS[self.phase]

    @property
    def average_profit(self) -> int:
        """開店からの平均月次利益。"""
        if self.months_elapsed <= 0:
            return 0
        return _round_cents(Decimal(self.cumulative_profit) / self.months_elapsed)


@dataclass
class Scenario:
    """回収完了時期の予測シナリオ。"""

    key: str
    label: str
    monthly_profit: int
    months_needed: int | None = None
    finish_month: str | None = None

    @property
    def possible(self) -> bool:
        return self.months_needed is not None


@dataclass
class Capacity:
    """投資余力(次の一手に回せるお金)。"""

    cash: int = 0
    monthly_fixed_cost: int = 0
    reserve_months: int = DEFAULT_RESERVE_MONTHS

    @property
    def reserve_needed(self) -> int:
        """手元に残す運転資金。"""
        return self.monthly_fixed_cost * self.reserve_months

    @property
    def available(self) -> int:
        """いま投資に回せる額。"""
        return max(0, self.cash - self.reserve_needed)


@dataclass
class PlanStatus:
    """「次にやれること」の到達状況。"""

    name: str
    amount: int
    memo: str = ""
    id: int | None = None
    available: int = 0
    monthly_profit: int = 0
    last_month: str | None = None

    @property
    def funded(self) -> bool:
        """いまの投資余力で実行できるか。"""
        return self.amount > 0 and self.available >= self.amount

    @property
    def shortfall(self) -> int:
        return max(0, self.amount - self.available)

    @property
    def progress(self) -> float:
        if self.amount <= 0:
            return 0.0
        return round(min(100.0, self.available / self.amount * 100), 1)

    @property
    def months_needed(self) -> int | None:
        """あと何か月でその額に届くか。利益が出ていなければ None。"""
        if self.funded:
            return 0
        return months_to_cover(self.shortfall, self.monthly_profit)

    @property
    def ready_month(self) -> str | None:
        months = self.months_needed
        if months is None or self.last_month is None:
            return None
        return month_shift(self.last_month, months)


@dataclass
class Lifecycle:
    """開店からの累計・回収・予測をまとめたもの。"""

    payback: Payback
    history: list[CumulativePoint] = field(default_factory=list)
    forecast: list[CumulativePoint] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    capacity: Capacity = field(default_factory=Capacity)
    plans: list[PlanStatus] = field(default_factory=list)

    @property
    def points(self) -> list[CumulativePoint]:
        """実績 + 予測。"""
        return self.history + self.forecast


def build_history(months: list[MonthResult], investment: int) -> list[CumulativePoint]:
    """月次実績から累計推移を組み立てる。"""
    points: list[CumulativePoint] = []
    cumulative = 0
    for result in months:
        cumulative += result.profit
        points.append(
            CumulativePoint(
                month=result.month,
                revenue=result.revenue,
                profit=result.profit,
                net_income=result.net_income,
                cumulative_profit=cumulative,
                position=cumulative - investment,
                remaining=max(0, investment - cumulative),
                recovery_rate=(
                    round(max(0, cumulative) / investment * 100, 1) if investment > 0 else 0.0
                ),
            )
        )
    return points


def evaluate_payback(
    months: list[MonthResult],
    investment: int,
    recent_months: int = RECENT_MONTHS,
) -> Payback:
    """初期投資の回収状況を評価する。"""
    active = [m for m in months if m.has_activity]
    payback = Payback(investment=investment, recent_months=0)
    if not active:
        return payback

    points = build_history(active, investment)
    payback.months_elapsed = len(active)
    payback.cumulative_profit = points[-1].cumulative_profit
    payback.cumulative_net_income = sum(m.net_income for m in active)
    payback.profitable_months = sum(1 for m in active if m.profit > 0)
    payback.last_month = active[-1].month

    for result in active:
        if result.profit > 0:
            payback.first_profitable_month = result.month
            break

    if investment > 0:
        for point in points:
            if point.position >= 0:
                payback.payback_month = point.month
                break

    worst = min(points, key=lambda p: p.position)
    payback.worst_position = worst.position
    payback.worst_month = worst.month

    window = active[-recent_months:]
    payback.recent_months = len(window)
    payback.recent_average_profit = _round_cents(
        Decimal(sum(m.profit for m in window)) / len(window)
    )
    return payback


def forecast_scenarios(
    payback: Payback, target_min: int, target_max: int
) -> list[Scenario]:
    """回収完了時期を 3 つのペースで予測する。"""
    scenarios = [
        Scenario(
            key="recent",
            label=f"直近 {payback.recent_months} か月平均"
            if payback.recent_months
            else "直近実績",
            monthly_profit=payback.recent_average_profit,
        ),
        Scenario(key="target_min", label="目標下限のペース", monthly_profit=target_min),
        Scenario(key="target_max", label="目標上限のペース", monthly_profit=target_max),
    ]
    for scenario in scenarios:
        scenario.months_needed = months_to_cover(payback.remaining, scenario.monthly_profit)
        if scenario.months_needed is not None and payback.last_month:
            scenario.finish_month = month_shift(payback.last_month, scenario.months_needed)
    return scenarios


def project(
    payback: Payback, monthly_profit: int, months: int
) -> list[CumulativePoint]:
    """今の利益ペースが続いた場合の累計推移を先の月まで伸ばす。"""
    if not payback.last_month or months <= 0:
        return []
    points = []
    cumulative = payback.cumulative_profit
    for offset in range(1, months + 1):
        cumulative += monthly_profit
        points.append(
            CumulativePoint(
                month=month_shift(payback.last_month, offset),
                revenue=0,
                profit=monthly_profit,
                net_income=0,
                cumulative_profit=cumulative,
                position=cumulative - payback.investment,
                remaining=max(0, payback.investment - cumulative),
                recovery_rate=(
                    round(max(0, cumulative) / payback.investment * 100, 1)
                    if payback.investment > 0
                    else 0.0
                ),
                forecast=True,
            )
        )
    return points


def months_to_cover(amount: int, monthly_profit: int) -> int | None:
    """その利益ペースで amount を賄うのに必要な月数。赤字ペースなら None。"""
    if amount <= 0:
        return 0
    if monthly_profit <= 0:
        return None
    return -(-amount // monthly_profit)  # 切り上げ


def investment_capacity(
    cash: int, monthly_fixed_cost: int, reserve_months: int = DEFAULT_RESERVE_MONTHS
) -> Capacity:
    """現金と固定費から、次の投資に回せる額を出す。"""
    return Capacity(
        cash=cash,
        monthly_fixed_cost=monthly_fixed_cost,
        reserve_months=max(0, reserve_months),
    )


def evaluate_plans(
    plans: list[tuple[int | None, str, int, str]],
    capacity: Capacity,
    monthly_profit: int,
    last_month: str | None,
) -> list[PlanStatus]:
    """「次にやれること」の一覧に到達状況を付ける。"""
    return [
        PlanStatus(
            id=plan_id,
            name=name,
            amount=amount,
            memo=memo,
            available=capacity.available,
            monthly_profit=monthly_profit,
            last_month=last_month,
        )
        for plan_id, name, amount, memo in plans
    ]


def _round_cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
