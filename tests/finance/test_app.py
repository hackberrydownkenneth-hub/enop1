"""財務・経営指標システム(画面 / API)の統合テスト。"""

import io
from datetime import date

import pytest

from enop_finance import calc, create_app, kpi

MONTH = "2026-09"

PAYROLL_CSV = (
    "社員コード,氏名,出勤日数,実労働時間,残業時間,時給,基本給,残業手当,支給額合計\n"
    "E001,山田太郎,20,160.0,8.0,2000,320000,20000,340000\n"
    "E002,鈴木花子,18,144.0,0.0,1800,259200,0,259200\n"
)


@pytest.fixture()
def app(tmp_path):
    application = create_app(db_path=str(tmp_path / "enop.db"))
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as client:
        yield client


def _add(client, category, item, amount, month=MONTH, memo=None):
    resp = client.post(
        "/api/entries",
        json={"month": month, "category": category, "item": item,
              "amount": amount, "memo": memo},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["id"]


def _seed_month(client, month=MONTH):
    """売上 $240,000 / 営業利益 $75,000 の 1 か月分。"""
    _add(client, "revenue", "フード売上", 180_000, month)
    _add(client, "revenue", "ドリンク売上", 60_000, month)
    _add(client, "cogs", "食材原価", 72_000, month)
    _add(client, "labor", "社員給与", 60_000, month)
    _add(client, "opex", "家賃", 25_000, month)
    _add(client, "opex", "水道光熱費", 8_000, month)


# ---- PL・BS の API ---------------------------------------------------------

def test_statements_api_empty_month(client):
    data = client.get(f"/api/statements?month={MONTH}").get_json()
    assert data["month"] == MONTH
    assert data["pl"]["totals"]["operating_income"] == 0
    assert data["target"]["target_min"] == 30_000
    assert data["target"]["target_max"] == 50_000
    assert data["target"]["status"] == calc.STATUS_BELOW


def test_statements_api_totals(client):
    _seed_month(client)
    totals = client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["revenue"] == 240_000
    assert totals["gross_profit"] == 168_000
    assert totals["operating_income"] == 75_000


def test_statements_api_balance_sheet(client):
    _add(client, "current_asset", "現金預金", 120_000)
    _add(client, "fixed_asset", "内装設備", 300_000)
    _add(client, "current_liability", "買掛金", 40_000)
    _add(client, "long_liability", "長期借入金", 200_000)
    _add(client, "equity", "資本金", 180_000)
    bs = client.get(f"/api/statements?month={MONTH}").get_json()["bs"]
    assert bs["totals"]["total_assets"] == 420_000
    assert bs["balanced"] is True


def test_entry_api_rejects_invalid_input(client):
    for payload in (
        {"category": "unknown", "item": "x", "amount": 1},
        {"category": "revenue", "item": "", "amount": 1},
        {"category": "revenue", "item": "売上", "amount": "abc"},
    ):
        resp = client.post("/api/entries", json={"month": MONTH, **payload})
        assert resp.status_code == 400


def test_entry_api_delete(client):
    entry_id = _add(client, "opex", "広告費", 5_000)
    assert client.delete(f"/api/entries/{entry_id}").status_code == 200
    assert client.delete(f"/api/entries/{entry_id}").status_code == 404
    totals = client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["opex"] == 0


def test_target_api_override_is_per_month(client):
    assert client.put(
        "/api/target", json={"month": MONTH, "target_min": 40_000, "target_max": 60_000}
    ).status_code == 200
    target = client.get(f"/api/statements?month={MONTH}").get_json()["target"]
    assert (target["target_min"], target["target_max"]) == (40_000, 60_000)
    other = client.get("/api/statements?month=2026-10").get_json()["target"]
    assert (other["target_min"], other["target_max"]) == (30_000, 50_000)


def test_invalid_month_falls_back_to_current(client):
    data = client.get("/api/statements?month=2026-99").get_json()
    assert data["month"] == date.today().strftime("%Y-%m")


# ---- KPI の API ------------------------------------------------------------

def test_kpi_api_reports_every_indicator_group(client):
    _seed_month(client)
    _add(client, "current_asset", "現金預金", 120_000)
    client.put(
        "/api/kpi-inputs",
        json={"month": MONTH, "customers": 4_800, "open_days": 25},
    )

    data = client.get(f"/api/kpi?month={MONTH}").get_json()
    assert data["target"]["profit"] == 75_000
    assert data["target"]["status"] == calc.STATUS_ABOVE

    assert data["sales"]["revenue"] == 240_000
    assert data["sales"]["customers"] == 4_800
    assert data["sales"]["average_spend"] == 50.0
    assert data["sales"]["daily_sales"] == 9_600.0

    assert data["cost_ratios"]["food_ratio"] == 30.0
    assert data["cost_ratios"]["labor_ratio"] == 25.0
    assert data["cost_ratios"]["fl_ratio"] == 55.0
    assert data["cost_ratios"]["fl_level"] == kpi.LEVEL_GOOD

    assert data["cash"]["cash_balance"] == 120_000
    assert data["cash"]["estimated"] is True
    assert data["cash"]["monthly_burn"] == 0
    assert data["cash"]["runway_months"] is None
    assert data["cash"]["breakeven_revenue"] == 132_857.14


def test_kpi_api_runway_when_in_the_red(client):
    _add(client, "opex", "家賃", 20_000)
    client.put("/api/kpi-inputs", json={"month": MONTH, "cash_balance": 100_000})
    cash = client.get(f"/api/kpi?month={MONTH}").get_json()["cash"]
    assert cash["cash_balance"] == 100_000
    assert cash["estimated"] is False
    assert cash["monthly_burn"] == 20_000
    assert cash["runway_months"] == 5.0


def test_kpi_api_trend_starts_at_the_first_month_with_data(client):
    # 開店前の空月は推移から落とす
    _seed_month(client, "2026-08")
    _seed_month(client, MONTH)
    data = client.get(f"/api/kpi?month={MONTH}").get_json()
    assert [p["month"] for p in data["trend"]] == ["2026-08", MONTH]
    assert data["trend"][-1]["operating_income"] == 75_000
    assert data["trend_summary"]["months"] == 2
    assert data["trend_summary"]["achieved_months"] == 2


def test_kpi_api_trend_is_capped_at_the_configured_length(app, client):
    app.config["TREND_MONTHS"] = 3
    for offset, month in enumerate(["2026-06", "2026-07", "2026-08", MONTH]):
        _seed_month(client, month)
    data = client.get(f"/api/kpi?month={MONTH}").get_json()
    assert [p["month"] for p in data["trend"]] == ["2026-07", "2026-08", MONTH]


def test_kpi_api_trend_without_any_data(client):
    data = client.get(f"/api/kpi?month={MONTH}").get_json()
    assert [p["month"] for p in data["trend"]] == [MONTH]
    assert data["trend_summary"]["months"] == 0


def test_kpi_inputs_api_validates(client):
    resp = client.put("/api/kpi-inputs", json={"month": MONTH, "open_days": 40})
    assert resp.status_code == 400
    resp = client.put("/api/kpi-inputs", json={"month": MONTH, "cash_balance": "たくさん"})
    assert resp.status_code == 400


# ---- 給与 CSV の取り込み ---------------------------------------------------

def test_payroll_csv_import_api(app, client):
    app.config["JPY_PER_USD"] = 150.0
    resp = client.post("/api/import/payroll", json={"month": MONTH, "csv": PAYROLL_CSV})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["employees"] == 2
    assert body["total_yen"] == 599_200
    assert body["amount"] == 3_994.67          # ¥599,200 ÷ 150

    totals = client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["labor_cost"] == 3_994.67


def test_payroll_csv_import_replaces_previous_import(client):
    client.post("/api/import/payroll", json={"month": MONTH, "csv": PAYROLL_CSV})
    client.post("/api/import/payroll", json={"month": MONTH, "csv": PAYROLL_CSV})
    labor = [
        s for s in client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["sections"]
        if s["category"] == "labor"
    ][0]
    assert len(labor["lines"]) == 1
    assert labor["lines"][0]["source"] == calc.SOURCE_IMPORT


def test_payroll_csv_import_keeps_manual_labor_entries(client):
    _add(client, "labor", "社員給与(手入力)", 10_000)
    client.post("/api/import/payroll", json={"month": MONTH, "csv": PAYROLL_CSV})
    labor = [
        s for s in client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["sections"]
        if s["category"] == "labor"
    ][0]
    assert len(labor["lines"]) == 2


def test_payroll_csv_import_rejects_wrong_format(client):
    resp = client.post("/api/import/payroll", json={"month": MONTH, "csv": "氏名\n山田\n"})
    assert resp.status_code == 400


def test_payroll_csv_import_via_form(client):
    data = {
        "month": MONTH,
        "payroll_csv": (io.BytesIO(("﻿" + PAYROLL_CSV).encode("utf-8")), "payroll.csv"),
    }
    resp = client.post(
        "/import/payroll", data=data, content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "取り込みました" in resp.data.decode()


def test_payroll_csv_import_form_requires_a_file(client):
    resp = client.post(
        "/import/payroll", data={"month": MONTH}, content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "給与 CSV ファイルを選択してください" in resp.data.decode()


# ---- 画面 ------------------------------------------------------------------

def test_dashboard_renders_all_indicator_groups(client):
    _seed_month(client)
    _add(client, "current_asset", "現金預金", 120_000)
    client.put("/api/kpi-inputs", json={"month": MONTH, "customers": 4_800, "open_days": 25})

    body = client.get(f"/?month={MONTH}").data.decode()
    assert "$75,000.00" in body            # 営業利益
    assert "目標超過" in body
    assert "客単価" in body and "$50.00" in body
    assert "FL 比率" in body and "55.0%" in body
    assert "ランウェイ" in body
    assert "推移" in body


def test_dashboard_renders_without_any_data(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "未達" in resp.data.decode()


def test_statements_page_renders(client):
    _seed_month(client)
    body = client.get(f"/statements?month={MONTH}").data.decode()
    assert "損益計算書" in body
    assert "貸借対照表" in body
    assert "フード売上" in body
    assert "$75,000.00" in body


def test_statements_page_flags_unbalanced_sheet(client):
    _add(client, "current_asset", "現金預金", 100_000)
    _add(client, "equity", "資本金", 60_000)
    assert "貸借差額" in client.get(f"/statements?month={MONTH}").data.decode()


def test_add_and_delete_entry_via_form(client):
    resp = client.post(
        "/entries",
        data={"month": MONTH, "category": "opex", "item": "広告費",
              "amount": "1,500.50", "memo": "SNS 広告"},
        follow_redirects=True,
    )
    assert "広告費" in resp.data.decode()

    sections = client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["sections"]
    opex = [s for s in sections if s["category"] == "opex"][0]
    assert opex["total"] == 1_500.5

    client.post(f"/entries/{opex['lines'][0]['id']}/delete", data={"month": MONTH})
    totals = client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["opex"] == 0


def test_entry_form_rejects_invalid_amount(client):
    resp = client.post(
        "/entries",
        data={"month": MONTH, "category": "revenue", "item": "売上", "amount": "たくさん"},
        follow_redirects=True,
    )
    assert "金額として解釈できません" in resp.data.decode()


def test_kpi_form_saves_inputs(client):
    resp = client.post(
        "/kpi",
        data={"month": MONTH, "customers": "3000", "open_days": "26",
              "cash_balance": "80,000"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    data = client.get(f"/api/kpi?month={MONTH}").get_json()
    assert data["sales"]["customers"] == 3_000
    assert data["sales"]["open_days"] == 26
    assert data["cash"]["cash_balance"] == 80_000


def test_target_form_saves_target(client):
    client.post(
        "/target",
        data={"month": MONTH, "target_min": "35000", "target_max": "55000"},
        follow_redirects=True,
    )
    target = client.get(f"/api/statements?month={MONTH}").get_json()["target"]
    assert (target["target_min"], target["target_max"]) == (35_000, 55_000)


def test_copy_previous_month(client):
    _seed_month(client, "2026-08")
    resp = client.post(
        "/copy", data={"month": MONTH, "from_month": "2026-08"}, follow_redirects=True
    )
    assert "複製しました" in resp.data.decode()
    assert client.get(f"/api/statements?month={MONTH}").get_json()["pl"]["totals"]["revenue"] == 240_000
    assert client.get("/api/statements?month=2026-08").get_json()["pl"]["totals"]["revenue"] == 240_000


def test_copy_requires_source_entries(client):
    resp = client.post(
        "/copy", data={"month": MONTH, "from_month": "2026-08"}, follow_redirects=True
    )
    assert "複製できる明細がありません" in resp.data.decode()


def test_report_csv_includes_statements_and_kpi(client):
    _seed_month(client)
    _add(client, "current_asset", "現金預金", 120_000)
    client.put("/api/kpi-inputs", json={"month": MONTH, "customers": 4_800, "open_days": 25})

    resp = client.get(f"/report.csv?month={MONTH}")
    assert resp.status_code == 200
    assert f"enop_{MONTH}.csv" in resp.headers["Content-Disposition"]
    body = resp.data.decode("utf-8-sig")
    assert "フード売上" in body
    assert "営業利益,,75000.0" in body
    assert "現金預金" in body
    assert "客単価,50.0,USD" in body
    assert "FL 比率,55.0,%" in body


# ---- 累計・投資回収 --------------------------------------------------------

def _seed_opening(client):
    """オープンコスト $360,000 と、開店 3 か月分の実績。"""
    for item, amount in [("内装工事", 180_000), ("厨房機器", 95_000),
                         ("保証金", 60_000), ("開業前家賃・採用", 25_000)]:
        resp = client.post("/api/startup-costs", json={"item": item, "amount": amount})
        assert resp.status_code == 201, resp.data
    # 2026-04 は赤字、以降は黒字
    for month, revenue, opex in [("2026-04", 118_000, 45_000),
                                 ("2026-05", 152_000, 45_000),
                                 ("2026-06", 181_000, 45_000)]:
        _add(client, "revenue", "売上", revenue, month)
        _add(client, "cogs", "原価", round(revenue * 0.32, 2), month)
        _add(client, "labor", "人件費", 50_000, month)
        _add(client, "opex", "家賃ほか", opex, month)


def test_lifecycle_api_tracks_cumulative_and_payback(client):
    _seed_opening(client)
    data = client.get("/api/lifecycle?month=2026-06").get_json()

    assert data["investment"] == 360_000
    payback = data["payback"]
    assert payback["months_elapsed"] == 3
    assert payback["profitable_months"] == 2
    assert payback["first_profitable_month"] == "2026-05"
    assert payback["cumulative_profit"] == 21_680
    assert payback["position"] == -338_320
    assert payback["remaining"] == 338_320
    assert payback["recovered"] is False
    assert payback["payback_month"] is None
    assert payback["worst_month"] == "2026-04"
    assert payback["phase"] == "earning"


def test_lifecycle_api_history_and_forecast(client):
    _seed_opening(client)
    data = client.get("/api/lifecycle?month=2026-06").get_json()
    assert [p["month"] for p in data["history"]] == ["2026-04", "2026-05", "2026-06"]
    assert data["history"][0]["position"] == -374_760      # 投資 + 初月の赤字
    assert data["history"][-1]["position"] == -338_320
    # 予測は直近ペースで先へ伸びる
    assert len(data["forecast"]) == 6
    assert all(p["forecast"] for p in data["forecast"])
    assert data["forecast"][0]["month"] == "2026-07"
    assert data["forecast"][-1]["position"] > data["history"][-1]["position"]


def test_lifecycle_api_scenarios(client):
    _seed_opening(client)
    scenarios = {s["key"]: s for s in client.get(
        "/api/lifecycle?month=2026-06").get_json()["scenarios"]}
    # 残り $338,320 を月 $30,000 / $50,000 で
    assert scenarios["target_min"]["months_needed"] == 12
    assert scenarios["target_min"]["finish_month"] == "2027-06"
    assert scenarios["target_max"]["months_needed"] == 7
    assert scenarios["recent"]["monthly_profit"] == 7_226.67


def test_lifecycle_api_reports_recovery(client):
    _seed_opening(client)
    _add(client, "revenue", "特別売上", 500_000, "2026-07")
    data = client.get("/api/lifecycle?month=2026-07").get_json()
    assert data["payback"]["recovered"] is True
    assert data["payback"]["payback_month"] == "2026-07"
    assert data["payback"]["surplus"] > 0
    assert data["scenarios"][0]["months_needed"] == 0


def test_lifecycle_api_capacity_and_plans(client):
    _seed_opening(client)
    client.put("/api/kpi-inputs", json={"month": "2026-06", "cash_balance": 400_000})
    client.post("/api/plans", json={"name": "2 号店の出店", "amount": 300_000})

    data = client.get("/api/lifecycle?month=2026-06").get_json()
    capacity = data["capacity"]
    assert capacity["cash"] == 400_000
    assert capacity["monthly_fixed_cost"] == 95_000        # 人件費 + 販管費
    assert capacity["reserve_needed"] == 285_000           # 3 か月分
    assert capacity["available"] == 115_000

    plan = data["plans"][0]
    assert plan["name"] == "2 号店の出店"
    assert plan["funded"] is False
    assert plan["shortfall"] == 185_000
    assert plan["months_needed"] == 26                     # 直近ペース $7,226.67


def test_lifecycle_api_without_any_data(client):
    data = client.get(f"/api/lifecycle?month={MONTH}").get_json()
    assert data["investment"] == 0
    assert data["payback"]["phase"] == "pre_open"
    assert data["history"] == []
    assert data["forecast"] == []


def test_startup_cost_api_add_and_delete(client):
    resp = client.post(
        "/api/startup-costs",
        json={"item": "内装工事", "amount": 180_000, "cost_month": "2026-03"},
    )
    assert resp.status_code == 201
    cost_id = resp.get_json()["id"]
    assert client.get("/api/lifecycle").get_json()["investment"] == 180_000

    assert client.delete(f"/api/startup-costs/{cost_id}").status_code == 200
    assert client.delete(f"/api/startup-costs/{cost_id}").status_code == 404
    assert client.get("/api/lifecycle").get_json()["investment"] == 0


def test_startup_cost_api_validates(client):
    assert client.post("/api/startup-costs", json={"item": "", "amount": 1}).status_code == 400
    assert client.post(
        "/api/startup-costs", json={"item": "内装", "amount": "たくさん"}
    ).status_code == 400


def test_plan_api_add_and_delete(client):
    resp = client.post("/api/plans", json={"name": "2 号店", "amount": 300_000})
    assert resp.status_code == 201
    plan_id = resp.get_json()["id"]
    assert len(client.get("/api/lifecycle").get_json()["plans"]) == 1
    assert client.delete(f"/api/plans/{plan_id}").status_code == 200
    assert client.delete(f"/api/plans/{plan_id}").status_code == 404


def test_plan_api_validates(client):
    assert client.post("/api/plans", json={"name": "", "amount": 1}).status_code == 400


def test_lifecycle_page_renders(client):
    _seed_opening(client)
    client.post("/api/plans", json={"name": "2 号店の出店", "amount": 300_000})
    body = client.get("/lifecycle?month=2026-06").data.decode()
    assert "通算損益" in body
    assert "-$338,320.00" in body            # 通算損益
    assert "オープンコスト" in body and "$360,000.00" in body
    assert "回収はいつ終わるか" in body
    assert "2 号店の出店" in body
    assert "内装工事" in body


def test_lifecycle_page_without_data(client):
    body = client.get("/lifecycle").data.decode()
    assert "オープンコストが未登録です" in body
    assert "まだ実績がありません" in body


def test_startup_cost_form_add_and_delete(client):
    resp = client.post(
        "/startup-costs",
        data={"month": MONTH, "item": "内装工事", "amount": "180,000",
              "cost_month": "2026-03", "memo": "A 社"},
        follow_redirects=True,
    )
    assert "内装工事" in resp.data.decode()
    cost_id = client.get("/api/lifecycle").get_json()["investment"]
    assert cost_id == 180_000

    client.post("/startup-costs/1/delete", data={"month": MONTH})
    assert client.get("/api/lifecycle").get_json()["investment"] == 0


def test_startup_cost_form_rejects_invalid_amount(client):
    resp = client.post(
        "/startup-costs",
        data={"month": MONTH, "item": "内装工事", "amount": "たくさん"},
        follow_redirects=True,
    )
    assert "金額として解釈できません" in resp.data.decode()


def test_plan_form_add_and_delete(client):
    resp = client.post(
        "/plans",
        data={"month": MONTH, "name": "2 号店の出店", "amount": "300000", "memo": "駅前"},
        follow_redirects=True,
    )
    assert "2 号店の出店" in resp.data.decode()
    client.post("/plans/1/delete", data={"month": MONTH})
    assert client.get("/api/lifecycle").get_json()["plans"] == []


def test_dashboard_shows_cumulative_summary(client):
    _seed_opening(client)
    body = client.get("/?month=2026-06").data.decode()
    assert "通算損益(オープンコスト込み)" in body
    assert "投資回収" in body
    assert "回収中(単月黒字)" in body
