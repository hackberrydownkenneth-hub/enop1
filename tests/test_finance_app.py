"""PL・BS 管理画面 / API の統合テスト。"""

from datetime import datetime, date

import pytest

from timecard import create_app, db, finance

MONTH = "2026-09"


@pytest.fixture()
def app(tmp_path):
    application = create_app(db_path=str(tmp_path / "finance.db"))
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as client:
        yield client


def _add(client, category, item, amount, month=MONTH, memo=None):
    resp = client.post(
        "/api/finance/entries",
        json={"month": month, "category": category, "item": item,
              "amount": amount, "memo": memo},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["id"]


def _seed_month(client, month=MONTH):
    """営業利益 $75,000 になる 1 か月分の明細。"""
    _add(client, "revenue", "フード売上", 180_000, month)
    _add(client, "revenue", "ドリンク売上", 60_000, month)
    _add(client, "cogs", "食材原価", 72_000, month)
    _add(client, "labor", "社員給与", 60_000, month)
    _add(client, "opex", "家賃", 25_000, month)
    _add(client, "opex", "水道光熱費", 8_000, month)


# ---- API -------------------------------------------------------------------

def test_finance_api_empty_month(client):
    data = client.get(f"/api/finance?month={MONTH}").get_json()
    assert data["month"] == MONTH
    assert data["pl"]["totals"]["operating_income"] == 0
    assert data["target"]["target_min"] == 30_000
    assert data["target"]["target_max"] == 50_000
    assert data["target"]["status"] == finance.STATUS_BELOW
    assert data["target"]["gap_to_min"] == 30_000


def test_finance_api_totals_and_target(client):
    _seed_month(client)
    data = client.get(f"/api/finance?month={MONTH}").get_json()
    totals = data["pl"]["totals"]
    assert totals["revenue"] == 240_000
    assert totals["gross_profit"] == 168_000
    assert totals["operating_income"] == 75_000
    assert data["target"]["status"] == finance.STATUS_ABOVE
    assert data["target"]["achieved"] is True
    assert data["target"]["annual_run_rate"] == 900_000


def test_finance_api_reports_breakeven_and_needed_revenue(client):
    _seed_month(client)
    data = client.get(f"/api/finance?month={MONTH}").get_json()
    # 固定費 $93,000・変動費率 30% → 損益分岐点 $132,857.14
    assert data["breakeven_revenue"] == 132_857.14
    assert data["revenue_needed_for_target"] == 175_714.29


def test_finance_api_balance_sheet(client):
    _add(client, "current_asset", "現金預金", 120_000)
    _add(client, "fixed_asset", "内装設備", 300_000)
    _add(client, "current_liability", "買掛金", 40_000)
    _add(client, "long_liability", "長期借入金", 200_000)
    _add(client, "equity", "資本金", 180_000)

    bs = client.get(f"/api/finance?month={MONTH}").get_json()["bs"]
    assert bs["totals"]["total_assets"] == 420_000
    assert bs["totals"]["total_liabilities_and_equity"] == 420_000
    assert bs["balanced"] is True
    assert bs["equity_ratio"] == pytest.approx(42.9)


def test_finance_api_rejects_invalid_input(client):
    resp = client.post("/api/finance/entries",
                       json={"month": MONTH, "category": "unknown", "item": "x", "amount": 1})
    assert resp.status_code == 400
    resp = client.post("/api/finance/entries",
                       json={"month": MONTH, "category": "revenue", "item": "", "amount": 1})
    assert resp.status_code == 400
    resp = client.post("/api/finance/entries",
                       json={"month": MONTH, "category": "revenue", "item": "売上", "amount": "abc"})
    assert resp.status_code == 400


def test_finance_api_delete_entry(client):
    entry_id = _add(client, "opex", "広告費", 5_000)
    assert client.delete(f"/api/finance/entries/{entry_id}").status_code == 200
    assert client.delete(f"/api/finance/entries/{entry_id}").status_code == 404
    totals = client.get(f"/api/finance?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["opex"] == 0


def test_finance_api_target_override_is_per_month(client):
    resp = client.put("/api/finance/target",
                      json={"month": MONTH, "target_min": 40_000, "target_max": 60_000})
    assert resp.status_code == 200

    target = client.get(f"/api/finance?month={MONTH}").get_json()["target"]
    assert (target["target_min"], target["target_max"]) == (40_000, 60_000)

    other = client.get("/api/finance?month=2026-10").get_json()["target"]
    assert (other["target_min"], other["target_max"]) == (30_000, 50_000)


def test_finance_api_invalid_month_falls_back_to_current(client):
    data = client.get("/api/finance?month=2026-99").get_json()
    assert data["month"] == date.today().strftime("%Y-%m")


# ---- 給与計算との連携 ------------------------------------------------------

def _punch_day(conn, employee_id, day, start_hour, end_hour):
    db.add_punch(conn, employee_id, "in", datetime(2026, 9, day, start_hour, 0))
    db.add_punch(conn, employee_id, "out", datetime(2026, 9, day, end_hour, 0))


def test_payroll_is_imported_as_labor_cost(app, client):
    emp_id = client.post(
        "/api/employees", json={"code": "E001", "name": "山田太郎", "hourly_wage": 2000}
    ).get_json()["id"]
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        for day in (1, 2, 3):
            _punch_day(conn, emp_id, day, 9, 17)  # 8 時間 × 3 日 = ¥48,000
        conn.close()

    app.config["JPY_PER_USD"] = 150.0
    data = client.get(f"/api/finance?month={MONTH}").get_json()
    labor = [s for s in data["pl"]["sections"] if s["category"] == "labor"][0]
    assert labor["lines"][0]["source"] == finance.SOURCE_TIMECARD
    assert labor["total"] == 320.0            # ¥48,000 ÷ 150
    assert data["pl"]["totals"]["labor_cost"] == 320.0


def test_payroll_import_can_be_disabled(app, client):
    emp_id = client.post(
        "/api/employees", json={"code": "E001", "name": "山田太郎", "hourly_wage": 2000}
    ).get_json()["id"]
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        _punch_day(conn, emp_id, 1, 9, 17)
        conn.close()

    app.config["LINK_PAYROLL"] = False
    data = client.get(f"/api/finance?month={MONTH}").get_json()
    assert data["pl"]["totals"]["labor_cost"] == 0


# ---- 画面・フォーム --------------------------------------------------------

def test_finance_page_renders(client):
    _seed_month(client)
    resp = client.get(f"/finance?month={MONTH}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "損益計算書" in body
    assert "貸借対照表" in body
    assert "$75,000.00" in body       # 営業利益
    assert "$30,000.00" in body       # 目標下限
    assert "フード売上" in body


def test_finance_page_flags_unbalanced_sheet(client):
    _add(client, "current_asset", "現金預金", 100_000)
    _add(client, "equity", "資本金", 60_000)
    body = client.get(f"/finance?month={MONTH}").data.decode()
    assert "貸借差額" in body


def test_add_and_delete_entry_via_form(client):
    resp = client.post(
        "/finance/entries",
        data={"month": MONTH, "category": "opex", "item": "広告費",
              "amount": "1,500.50", "memo": "SNS 広告"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "広告費" in resp.data.decode()

    entries = client.get(f"/api/finance?month={MONTH}").get_json()["pl"]["sections"]
    opex = [s for s in entries if s["category"] == "opex"][0]
    assert opex["total"] == 1_500.5
    entry_id = opex["lines"][0]["id"]

    client.post(f"/finance/entries/{entry_id}/delete", data={"month": MONTH})
    totals = client.get(f"/api/finance?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["opex"] == 0


def test_form_rejects_invalid_amount(client):
    resp = client.post(
        "/finance/entries",
        data={"month": MONTH, "category": "revenue", "item": "売上", "amount": "たくさん"},
        follow_redirects=True,
    )
    assert "金額として解釈できません" in resp.data.decode()
    assert client.get(f"/api/finance?month={MONTH}").get_json()["pl"]["totals"]["revenue"] == 0


def test_set_target_via_form(client):
    resp = client.post(
        "/finance/target",
        data={"month": MONTH, "target_min": "35000", "target_max": "55000"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    target = client.get(f"/api/finance?month={MONTH}").get_json()["target"]
    assert (target["target_min"], target["target_max"]) == (35_000, 55_000)


def test_copy_previous_month(client):
    _seed_month(client, "2026-08")
    resp = client.post(
        "/finance/copy",
        data={"month": MONTH, "from_month": "2026-08"},
        follow_redirects=True,
    )
    assert "複製しました" in resp.data.decode()
    totals = client.get(f"/api/finance?month={MONTH}").get_json()["pl"]["totals"]
    assert totals["revenue"] == 240_000
    # 複製元は変わらない
    assert client.get("/api/finance?month=2026-08").get_json()["pl"]["totals"]["revenue"] == 240_000


def test_copy_requires_source_entries(client):
    resp = client.post(
        "/finance/copy",
        data={"month": MONTH, "from_month": "2026-08"},
        follow_redirects=True,
    )
    assert "複製できる明細がありません" in resp.data.decode()


def test_finance_csv_export(client):
    _seed_month(client)
    _add(client, "current_asset", "現金預金", 120_000)
    resp = client.get(f"/finance/report.csv?month={MONTH}")
    assert resp.status_code == 200
    assert f"finance_{MONTH}.csv" in resp.headers["Content-Disposition"]
    body = resp.data.decode("utf-8-sig")
    assert "フード売上" in body
    assert "営業利益,,75000.0" in body
    assert "現金預金" in body


def test_nav_links_to_finance(client):
    assert "/finance" in client.get("/").data.decode()
