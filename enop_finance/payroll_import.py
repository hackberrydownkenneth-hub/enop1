"""タイムカードシステムが出力する給与 CSV の取り込み(純粋関数)。

タイムカードとはデータベースを分けているため、人件費はエクスポートした
CSV(`/admin/payroll.csv`)を経由して PL に取り込む。金額は CSV に書かれた
まま(既定では HK$)集計し、換算は呼び出し側で行う。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

TOTAL_COLUMN = "支給額合計"
NAME_COLUMN = "氏名"


@dataclass
class PayrollImport:
    """給与 CSV の集計結果。金額は CSV の通貨単位のまま。"""

    total_amount: int = 0
    employees: int = 0
    names: list[str] = field(default_factory=list)


def parse_payroll_csv(text: str) -> PayrollImport:
    """給与 CSV を読み、支給額合計を集計する。

    タイムカード側の CSV は BOM 付き UTF-8 で出力されるため、BOM を取り除いて読む。
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or TOTAL_COLUMN not in reader.fieldnames:
        raise ValueError(
            f"給与 CSV の形式が違います({TOTAL_COLUMN} 列が見つかりません)。"
        )

    result = PayrollImport()
    for row in reader:
        raw = (row.get(TOTAL_COLUMN) or "").strip().replace(",", "").replace("HK$", "").replace("$", "")
        if not raw:
            continue
        try:
            amount = int(round(float(raw)))
        except ValueError as exc:
            raise ValueError(f"支給額として読めない値があります: {raw!r}") from exc
        result.total_amount += amount
        result.employees += 1
        name = (row.get(NAME_COLUMN) or "").strip()
        if name:
            result.names.append(name)

    if result.employees == 0:
        raise ValueError("給与 CSV に取り込める行がありません。")
    return result
