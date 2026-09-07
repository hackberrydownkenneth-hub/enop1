"""給与 CSV 取り込みのユニットテスト。"""

import pytest

from enop_finance import payroll_import

CSV = (
    "社員コード,氏名,出勤日数,実労働時間,残業時間,時給,基本給,残業手当,支給額合計\n"
    "E001,山田太郎,20,160.0,8.0,2000,320000,20000,340000\n"
    "E002,鈴木花子,18,144.0,0.0,1800,259200,0,259200\n"
)


def test_parse_payroll_csv():
    result = payroll_import.parse_payroll_csv(CSV)
    assert result.employees == 2
    assert result.total_yen == 599_200
    assert result.names == ["山田太郎", "鈴木花子"]


def test_parse_payroll_csv_with_bom():
    result = payroll_import.parse_payroll_csv("﻿" + CSV)
    assert result.total_yen == 599_200


def test_parse_payroll_csv_skips_blank_rows():
    result = payroll_import.parse_payroll_csv(CSV + "E003,休職中,0,0,0,1500,,,\n")
    assert result.employees == 2


def test_parse_payroll_csv_rejects_wrong_format():
    with pytest.raises(ValueError):
        payroll_import.parse_payroll_csv("氏名,金額\n山田,1000\n")


def test_parse_payroll_csv_rejects_empty_file():
    with pytest.raises(ValueError):
        payroll_import.parse_payroll_csv(
            "社員コード,氏名,支給額合計\n"
        )
