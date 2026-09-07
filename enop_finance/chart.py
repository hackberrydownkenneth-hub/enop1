"""ダッシュボードの推移グラフ(インライン SVG)の座標計算(純粋関数)。

JavaScript もグラフライブラリも使わず、サーバー側で棒の座標を組み立てて
テンプレートは描画するだけにする。金額はセントで受け取る。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# 棒の仕様(marks: 24px 以下・データ側の角は 4px・棒どうしは 2px 空ける)
MAX_BAR_WIDTH = 24.0
BAR_RADIUS = 4.0
BAR_GAP = 2.0

# 余白
PAD_LEFT = 56.0
PAD_RIGHT = 12.0
PAD_TOP = 16.0
PAD_BOTTOM = 26.0


@dataclass
class Bar:
    """棒 1 本。SVG の rect にそのまま渡せる座標を持つ。"""

    label: str          # 月(2026-09 → 09)
    value: int          # 金額(セント)
    x: float
    y: float
    width: float
    height: float
    negative: bool = False
    tooltip: str = ""

    @property
    def radius(self) -> float:
        """棒が細い / 低いときに角丸が潰れないよう半径を抑える。"""
        return min(BAR_RADIUS, self.width / 2, max(self.height, 0.1))

    @property
    def label_x(self) -> float:
        return self.x + self.width / 2


@dataclass
class Tick:
    """Y 軸の目盛り。"""

    y: float
    label: str


@dataclass
class BarChart:
    """棒グラフ 1 枚分の描画データ。"""

    width: float
    height: float
    baseline_y: float
    bars: list[Bar] = field(default_factory=list)
    ticks: list[Tick] = field(default_factory=list)
    reference_y: float | None = None   # 目標ラインの Y 座標
    reference_label: str = ""
    has_data: bool = False

    @property
    def view_box(self) -> str:
        return f"0 0 {self.width:g} {self.height:g}"

    @property
    def plot_left(self) -> float:
        return PAD_LEFT

    @property
    def plot_right(self) -> float:
        return self.width - PAD_RIGHT


def bar_chart(
    points: list[tuple[str, int]],
    width: float = 640.0,
    height: float = 180.0,
    reference: int | None = None,
    reference_label: str = "",
) -> BarChart:
    """(ラベル, 金額)の並びから棒グラフの座標を組み立てる。

    金額がマイナスの月は基準線の下に伸びる。reference を渡すと目標ラインを引く。
    """
    chart = BarChart(width=width, height=height, baseline_y=height - PAD_BOTTOM)
    if not points:
        return chart

    values = [value for _label, value in points]
    top = max(values + ([reference] if reference is not None else []) + [0])
    bottom = min(values + [0])
    chart.has_data = any(values)

    top_nice = _nice_ceiling(top) if top > 0 else 0
    bottom_nice = -_nice_ceiling(-bottom) if bottom < 0 else 0
    span = top_nice - bottom_nice or 1

    plot_top = PAD_TOP
    plot_height = height - PAD_TOP - PAD_BOTTOM
    plot_left = PAD_LEFT
    plot_width = width - PAD_LEFT - PAD_RIGHT

    def y_of(value: int) -> float:
        return plot_top + (top_nice - value) / span * plot_height

    chart.baseline_y = y_of(0)

    band = plot_width / len(points)
    bar_width = min(MAX_BAR_WIDTH, max(4.0, band - BAR_GAP * 2))

    for index, (label, value) in enumerate(points):
        center = plot_left + band * (index + 0.5)
        y_value = y_of(value)
        bar = Bar(
            label=label,
            value=value,
            x=center - bar_width / 2,
            y=min(y_value, chart.baseline_y),
            width=bar_width,
            height=abs(chart.baseline_y - y_value),
            negative=value < 0,
        )
        chart.bars.append(bar)

    chart.ticks = [Tick(y=y_of(0), label=format_compact(0))]
    if top_nice:
        chart.ticks.insert(0, Tick(y=y_of(top_nice), label=format_compact(top_nice)))
    if bottom_nice:
        chart.ticks.append(Tick(y=y_of(bottom_nice), label=format_compact(bottom_nice)))

    if reference is not None and bottom_nice <= reference <= top_nice:
        chart.reference_y = y_of(reference)
        chart.reference_label = reference_label or format_compact(reference)

    return chart


def format_compact(cents: int) -> str:
    """軸ラベル用に金額を短く整形する($240k / $1.2M)。"""
    dollars = cents / 100
    sign = "-" if dollars < 0 else ""
    value = abs(dollars)
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{sign}${value / 1_000:.0f}k"
    return f"{sign}${value:,.0f}"


def _nice_ceiling(value: int) -> int:
    """目盛りが読みやすい値(1 / 2 / 5 × 10^n)に切り上げる。"""
    if value <= 0:
        return 0
    magnitude = Decimal(10) ** (len(str(int(value))) - 1)
    for factor in (Decimal(1), Decimal(2), Decimal(2.5), Decimal(5), Decimal(10)):
        candidate = magnitude * factor
        if Decimal(value) <= candidate:
            return int(candidate.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return value
