"""PL(損益計算書)・BS(貸借対照表)のドメインロジック(純粋関数)。

エノップの月次数字はすべてここで計算する。金額は丸め誤差を避けるため
「セント(1 ドルの 1/100)」の整数で保持し、表示時にドルへ戻す。
データベースや Web フレームワークには依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ---- 目標利益 --------------------------------------------------------------

# エノップ開店後の月次目標利益(ドル)。毎月この帯に着地させることが目標。
TARGET_MIN_USD = 30_000
TARGET_MAX_USD = 50_000
TARGET_MIN = TARGET_MIN_USD * 100  # セント
TARGET_MAX = TARGET_MAX_USD * 100  # セント

# 目標達成を判定する利益の種類
BASIS_OPERATING = "operating"  # 営業利益
BASIS_NET = "net"              # 当期純利益
DEFAULT_TARGET_BASIS = BASIS_OPERATING
BASIS_LABELS = {BASIS_OPERATING: "営業利益", BASIS_NET: "当期純利益"}

STATUS_BELOW = "below"        # 目標未達
STATUS_IN_RANGE = "in_range"  # 目標レンジ内
STATUS_ABOVE = "above"        # 目標超過
STATUS_LABELS = {
    STATUS_BELOW: "未達",
    STATUS_IN_RANGE: "目標達成",
    STATUS_ABOVE: "目標超過",
}

# ---- 勘定カテゴリ ----------------------------------------------------------

# PL のセクション(表示順)
PL_SECTIONS: tuple[tuple[str, str], ...] = (
    ("revenue", "売上高"),
    ("cogs", "売上原価"),
    ("labor", "人件費"),
    ("opex", "その他販管費"),
    ("other_income", "営業外収益"),
    ("other_expense", "営業外費用"),
    ("tax", "法人税等"),
)

# BS のセクション(表示順)
BS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("current_asset", "流動資産"),
    ("fixed_asset", "固定資産"),
    ("current_liability", "流動負債"),
    ("long_liability", "固定負債"),
    ("equity", "純資産"),
)

PL_CATEGORIES = tuple(code for code, _ in PL_SECTIONS)
BS_CATEGORIES = tuple(code for code, _ in BS_SECTIONS)
ASSET_CATEGORIES = ("current_asset", "fixed_asset")
LIABILITY_CATEGORIES = ("current_liability", "long_liability")

CATEGORY_LABELS = dict(PL_SECTIONS + BS_SECTIONS)
STATEMENT_OF = {code: "pl" for code in PL_CATEGORIES}
STATEMENT_OF.update({code: "bs" for code in BS_CATEGORIES})

# 固定費として扱うカテゴリ(損益分岐点の計算に使う)
FIXED_COST_CATEGORIES = ("labor", "opex")

SOURCE_MANUAL = "manual"      # 手入力
SOURCE_TIMECARD = "timecard"  # 打刻・給与計算から自動連携


@dataclass(frozen=True)
class Entry:
    """PL / BS の 1 明細。金額はセント。"""

    category: str
    item: str
    amount: int
    memo: str = ""
    id: int | None = None
    source: str = SOURCE_MANUAL

    @property
    def statement(self) -> str:
        return STATEMENT_OF.get(self.category, "")

    @property
    def editable(self) -> bool:
        return self.source == SOURCE_MANUAL


@dataclass
class Section:
    """カテゴリ単位の小計と明細。"""

    category: str
    label: str
    lines: list[Entry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(line.amount for line in self.lines)


@dataclass
class ProfitLoss:
    """1 か月分の損益計算書。"""

    month: str = ""
    sections: dict[str, Section] = field(default_factory=dict)

    @property
    def revenue(self) -> int:
        return self._total("revenue")

    @property
    def cogs(self) -> int:
        return self._total("cogs")

    @property
    def gross_profit(self) -> int:
        return self.revenue - self.cogs

    @property
    def labor_cost(self) -> int:
        return self._total("labor")

    @property
    def opex(self) -> int:
        return self._total("opex")

    @property
    def operating_cost(self) -> int:
        """販管費合計(人件費 + その他販管費)。"""
        return self.labor_cost + self.opex

    @property
    def operating_income(self) -> int:
        return self.gross_profit - self.operating_cost

    @property
    def other_income(self) -> int:
        return self._total("other_income")

    @property
    def other_expense(self) -> int:
        return self._total("other_expense")

    @property
    def ordinary_income(self) -> int:
        return self.operating_income + self.other_income - self.other_expense

    @property
    def tax(self) -> int:
        return self._total("tax")

    @property
    def net_income(self) -> int:
        return self.ordinary_income - self.tax

    @property
    def gross_margin(self) -> float:
        return _ratio(self.gross_profit, self.revenue)

    @property
    def operating_margin(self) -> float:
        return _ratio(self.operating_income, self.revenue)

    @property
    def net_margin(self) -> float:
        return _ratio(self.net_income, self.revenue)

    @property
    def is_empty(self) -> bool:
        return not any(section.lines for section in self.sections.values())

    def profit(self, basis: str = DEFAULT_TARGET_BASIS) -> int:
        """目標判定に使う利益を返す。"""
        return self.net_income if basis == BASIS_NET else self.operating_income

    def _total(self, category: str) -> int:
        section = self.sections.get(category)
        return section.total if section else 0


@dataclass
class BalanceSheet:
    """1 か月末時点の貸借対照表。"""

    month: str = ""
    sections: dict[str, Section] = field(default_factory=dict)

    @property
    def current_assets(self) -> int:
        return self._total("current_asset")

    @property
    def fixed_assets(self) -> int:
        return self._total("fixed_asset")

    @property
    def total_assets(self) -> int:
        return self.current_assets + self.fixed_assets

    @property
    def current_liabilities(self) -> int:
        return self._total("current_liability")

    @property
    def long_liabilities(self) -> int:
        return self._total("long_liability")

    @property
    def total_liabilities(self) -> int:
        return self.current_liabilities + self.long_liabilities

    @property
    def total_equity(self) -> int:
        return self._total("equity")

    @property
    def total_liabilities_and_equity(self) -> int:
        return self.total_liabilities + self.total_equity

    @property
    def difference(self) -> int:
        """資産 -(負債 + 純資産)。0 なら貸借一致。"""
        return self.total_assets - self.total_liabilities_and_equity

    @property
    def balanced(self) -> bool:
        return self.difference == 0

    @property
    def working_capital(self) -> int:
        """運転資本(流動資産 - 流動負債)。"""
        return self.current_assets - self.current_liabilities

    @property
    def current_ratio(self) -> float:
        """流動比率(%)。流動負債が 0 なら 0.0。"""
        return _ratio(self.current_assets, self.current_liabilities)

    @property
    def equity_ratio(self) -> float:
        """自己資本比率(%)。"""
        return _ratio(self.total_equity, self.total_assets)

    @property
    def is_empty(self) -> bool:
        return not any(section.lines for section in self.sections.values())

    def _total(self, category: str) -> int:
        section = self.sections.get(category)
        return section.total if section else 0


@dataclass
class TargetStatus:
    """月次目標(既定 $30,000〜$50,000)に対する到達状況。"""

    profit: int
    target_min: int = TARGET_MIN
    target_max: int = TARGET_MAX
    basis: str = DEFAULT_TARGET_BASIS

    @property
    def status(self) -> str:
        if self.profit < self.target_min:
            return STATUS_BELOW
        if self.profit > self.target_max:
            return STATUS_ABOVE
        return STATUS_IN_RANGE

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def basis_label(self) -> str:
        return BASIS_LABELS.get(self.basis, self.basis)

    @property
    def achieved(self) -> bool:
        """下限(既定 $30,000)に到達しているか。"""
        return self.profit >= self.target_min

    @property
    def gap_to_min(self) -> int:
        """下限までの不足額。達成済みなら 0。"""
        return max(0, self.target_min - self.profit)

    @property
    def gap_to_max(self) -> int:
        """上限までの残り。超過していれば 0。"""
        return max(0, self.target_max - self.profit)

    @property
    def surplus_over_max(self) -> int:
        """上限を超えた分。"""
        return max(0, self.profit - self.target_max)

    @property
    def achievement_rate(self) -> float:
        """下限に対する達成率(%)。"""
        return _ratio(self.profit, self.target_min)

    @property
    def progress(self) -> float:
        """進捗バー用に 0〜100 に丸めた達成率。"""
        return min(100.0, max(0.0, self.achievement_rate))

    @property
    def annual_run_rate(self) -> int:
        """この利益が 12 か月続いた場合の年間利益。"""
        return self.profit * 12


def compute_pl(entries: list[Entry], month: str = "") -> ProfitLoss:
    """明細から損益計算書を組み立てる。PL 以外のカテゴリは無視する。"""
    return ProfitLoss(month=month, sections=_build_sections(entries, PL_SECTIONS))


def compute_bs(entries: list[Entry], month: str = "") -> BalanceSheet:
    """明細から貸借対照表を組み立てる。BS 以外のカテゴリは無視する。"""
    return BalanceSheet(month=month, sections=_build_sections(entries, BS_SECTIONS))


def evaluate_target(
    profit: int,
    target_min: int = TARGET_MIN,
    target_max: int = TARGET_MAX,
    basis: str = DEFAULT_TARGET_BASIS,
) -> TargetStatus:
    """利益(セント)を月次目標と突き合わせる。"""
    if target_max < target_min:
        target_min, target_max = target_max, target_min
    return TargetStatus(
        profit=profit, target_min=target_min, target_max=target_max, basis=basis
    )


def variable_cost_ratio(pl: ProfitLoss) -> float:
    """変動費率。売上原価 ÷ 売上高。売上が無い月は 0.0。"""
    if pl.revenue <= 0:
        return 0.0
    return pl.cogs / pl.revenue


def fixed_cost(pl: ProfitLoss) -> int:
    """固定費(人件費 + その他販管費)。"""
    return sum(
        pl.sections[category].total
        for category in FIXED_COST_CATEGORIES
        if category in pl.sections
    )


def required_revenue(fixed: int, variable_ratio: float, target_profit: int = 0) -> int | None:
    """目標利益に必要な売上高を求める。

    必要売上 = (固定費 + 目標利益) ÷ (1 - 変動費率)
    変動費率が 1 以上(原価が売上を超える)の場合は算出不能として None を返す。
    """
    if not 0.0 <= variable_ratio < 1.0:
        return None
    needed = (Decimal(fixed) + Decimal(target_profit)) / (
        Decimal(1) - Decimal(str(variable_ratio))
    )
    return max(0, _round_cents(needed))


def breakeven_revenue(pl: ProfitLoss) -> int | None:
    """損益分岐点売上高(利益ゼロに必要な売上)。"""
    return required_revenue(fixed_cost(pl), variable_cost_ratio(pl))


def revenue_needed_for_target(
    pl: ProfitLoss, target_profit: int = TARGET_MIN
) -> int | None:
    """目標利益を出すために必要な売上高。現在の原価率・固定費を前提にする。"""
    return required_revenue(fixed_cost(pl), variable_cost_ratio(pl), target_profit)


# ---- 金額・月のユーティリティ ---------------------------------------------

def parse_amount(value: object) -> int:
    """ドル表記("1,234.56" や 1234.56)をセントの整数に変換する。"""
    if value is None:
        raise ValueError("金額が入力されていません。")
    text = str(value).strip().replace(",", "").replace("$", "").replace("¥", "")
    if not text:
        raise ValueError("金額が入力されていません。")
    try:
        return _round_cents(Decimal(text) * 100)
    except (InvalidOperation, ArithmeticError) as exc:
        raise ValueError(f"金額として解釈できません: {value!r}") from exc


def format_usd(cents: int, symbol: str = "$") -> str:
    """セントを表示用のドル文字列にする。"""
    sign = "-" if cents < 0 else ""
    dollars = Decimal(abs(int(cents))) / 100
    return f"{sign}{symbol}{dollars:,.2f}"


def to_dollars(cents: int) -> float:
    """セントをドル(float)に変換する。JSON 出力用。"""
    return round(cents / 100, 2)


def month_shift(month: str, delta: int) -> str:
    """'YYYY-MM' を delta か月ずらす。"""
    year, mon = (int(part) for part in month.split("-")[:2])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def validate_category(category: str, statement: str | None = None) -> str:
    """カテゴリの妥当性を検証して返す。不正なら ValueError。"""
    if category not in CATEGORY_LABELS:
        raise ValueError(f"不正なカテゴリです: {category!r}")
    if statement and STATEMENT_OF[category] != statement:
        raise ValueError(
            f"カテゴリ {category!r} は {STATEMENT_OF[category].upper()} の科目です。"
        )
    return category


def is_valid_month(month: str) -> bool:
    """'YYYY-MM' 形式かどうかを判定する。"""
    parts = month.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        return False
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    return 1 <= int(parts[1]) <= 12


# ---- 内部ヘルパー ----------------------------------------------------------

def _build_sections(
    entries: list[Entry], layout: tuple[tuple[str, str], ...]
) -> dict[str, Section]:
    sections = {code: Section(category=code, label=label) for code, label in layout}
    for entry in entries:
        section = sections.get(entry.category)
        if section is not None:
            section.lines.append(entry)
    return sections


def _ratio(numerator: int, denominator: int) -> float:
    """割合(%)を小数第 1 位で返す。分母が 0 なら 0.0。"""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _round_cents(amount: Decimal) -> int:
    """セント未満を四捨五入して整数にする。"""
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def yen_to_cents(yen: int, jpy_per_usd: float) -> int:
    """円建ての金額をドル建てのセントに換算する(給与→人件費の取り込み用)。"""
    if jpy_per_usd <= 0:
        raise ValueError("為替レートは正の数で指定してください。")
    return _round_cents(Decimal(yen) * 100 / Decimal(str(jpy_per_usd)))
