"""エノップ 財務・経営指標システムの Flask アプリケーション。

タイムカードとは独立したアプリ・独立したデータベースで動く。

- `/`            経営ダッシュボード(毎月ウォッチする指標)
- `/statements`  PL・BS の明細入力と表示
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import date

from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from . import calc, chart, db, kpi, payroll_import

DEFAULT_DB = os.environ.get("ENOP_DB", "enop_finance.db")
DEFAULT_TREND_MONTHS = 12


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or DEFAULT_DB
    app.secret_key = os.environ.get("ENOP_SECRET", "dev-enop-secret")

    # 月次の目標利益。既定はエノップ開店後の目標 $30,000〜$50,000。
    app.config["TARGET_MIN"] = _env_cents("ENOP_TARGET_MIN", calc.TARGET_MIN)
    app.config["TARGET_MAX"] = _env_cents("ENOP_TARGET_MAX", calc.TARGET_MAX)
    # 目標を判定する利益(operating: 営業利益 / net: 当期純利益)
    basis = os.environ.get("ENOP_TARGET_BASIS", calc.DEFAULT_TARGET_BASIS)
    app.config["TARGET_BASIS"] = (
        basis if basis in (calc.BASIS_OPERATING, calc.BASIS_NET)
        else calc.DEFAULT_TARGET_BASIS
    )
    # 給与 CSV(円)を人件費(ドル)に取り込むときの為替レート
    app.config["JPY_PER_USD"] = _env_float("ENOP_JPY_PER_USD", 150.0)
    # ダッシュボードに表示する推移の月数
    app.config["TREND_MONTHS"] = int(
        _env_float("ENOP_TREND_MONTHS", DEFAULT_TREND_MONTHS)
    )

    # テンプレートで金額を $1,234.56 形式に整形するフィルタ
    app.jinja_env.filters["usd"] = calc.format_usd

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = db.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(exception: BaseException | None = None) -> None:
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    with app.app_context():
        db.init_db(get_db())

    # ---- 画面 --------------------------------------------------------------

    @app.route("/")
    def dashboard():
        conn = get_db()
        month = _month_arg()
        metrics = _kpi(conn, month)
        prev = _kpi(conn, calc.month_shift(month, -1))
        points = _trend(conn, month, app.config["TREND_MONTHS"])
        return render_template(
            "dashboard.html",
            month=month,
            kpi=metrics,
            prev=prev,
            target=metrics.target,
            trend=points,
            revenue_chart=chart.bar_chart(
                [(p.month[-2:], p.revenue) for p in points]
            ),
            profit_chart=chart.bar_chart(
                [(p.month[-2:], p.operating_income) for p in points],
                reference=metrics.target.target_min,
                reference_label=chart.format_compact(metrics.target.target_min),
            ),
            summary=kpi.trend_summary(points),
            fl_good=kpi.FL_GOOD,
            fl_warn=kpi.FL_WARN,
            level_labels=kpi.LEVEL_LABELS,
            months=db.list_months(conn),
        )

    @app.route("/statements")
    def statements():
        conn = get_db()
        month = _month_arg()
        data = _statements(conn, month)
        prev_month = calc.month_shift(month, -1)
        return render_template(
            "statements.html",
            month=month,
            prev_month=prev_month,
            pl=data["pl"],
            bs=data["bs"],
            target=data["target"],
            prev_pl=_statements(conn, prev_month)["pl"],
            pl_sections=calc.PL_SECTIONS,
            bs_sections=calc.BS_SECTIONS,
            asset_categories=calc.ASSET_CATEGORIES,
            liability_categories=calc.LIABILITY_CATEGORIES,
            months=db.list_months(conn),
            jpy_per_usd=app.config["JPY_PER_USD"],
        )

    # ---- フォーム操作 ------------------------------------------------------

    @app.route("/entries", methods=["POST"])
    def add_entry_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            entry = _entry_input(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.add_entry(conn, month, *entry)
        return redirect(url_for("statements", month=month))

    @app.route("/entries/<int:entry_id>/delete", methods=["POST"])
    def delete_entry_form(entry_id: int):
        conn = get_db()
        row = db.get_entry(conn, entry_id)
        month = _month_arg(row["month"] if row else request.form.get("month"))
        db.delete_entry(conn, entry_id)
        return redirect(url_for("statements", month=month))

    @app.route("/target", methods=["POST"])
    def set_target_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            low = calc.parse_amount(request.form.get("target_min"))
            high = calc.parse_amount(request.form.get("target_max"))
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.set_target(conn, month, min(low, high), max(low, high))
        return redirect(request.referrer or url_for("dashboard", month=month))

    @app.route("/kpi", methods=["POST"])
    def save_kpi_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            customers, open_days, cash = _kpi_input(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.set_inputs(conn, month, customers, open_days, cash)
        return redirect(url_for("dashboard", month=month))

    @app.route("/copy", methods=["POST"])
    def copy_entries_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        source = _month_arg(request.form.get("from_month"))
        if source == month:
            flash("複製元と対象月が同じです。", "error")
            return redirect(url_for("statements", month=month))
        copied = db.copy_entries(conn, source, month)
        if copied:
            flash(f"{source} の明細 {copied} 件を {month} に複製しました。", "info")
        else:
            flash(f"{source} には複製できる明細がありません。", "error")
        return redirect(url_for("statements", month=month))

    @app.route("/import/payroll", methods=["POST"])
    def import_payroll_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        upload = request.files.get("payroll_csv")
        if upload is None or not upload.filename:
            flash("給与 CSV ファイルを選択してください。", "error")
            return redirect(url_for("statements", month=month))
        try:
            text = upload.read().decode("utf-8-sig")
            result = _import_payroll(conn, month, text)
        except (ValueError, UnicodeDecodeError) as exc:
            flash(f"給与 CSV を取り込めませんでした: {exc}", "error")
        else:
            flash(
                f"{result['employees']} 名分の給与 ¥{result['total_yen']:,} を "
                f"人件費 {calc.format_usd(result['amount'])} として取り込みました。",
                "info",
            )
        return redirect(url_for("statements", month=month))

    @app.route("/report.csv")
    def report_csv() -> Response:
        conn = get_db()
        month = _month_arg()
        data = _statements(conn, month)
        metrics = _kpi(conn, month)
        pl, bs, target = data["pl"], data["bs"], data["target"]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["対象月", month])
        writer.writerow([])
        writer.writerow(["区分", "カテゴリ", "科目", "金額(USD)", "備考"])
        for section in pl.sections.values():
            for line in section.lines:
                writer.writerow(
                    ["PL", section.label, line.item, calc.to_dollars(line.amount), line.memo]
                )
        writer.writerow([])
        for _key, label, value in _pl_totals(pl):
            writer.writerow(["PL 集計", label, "", calc.to_dollars(value), ""])
        writer.writerow([])
        for section in bs.sections.values():
            for line in section.lines:
                writer.writerow(
                    ["BS", section.label, line.item, calc.to_dollars(line.amount), line.memo]
                )
        writer.writerow([])
        for _key, label, value in _bs_totals(bs):
            writer.writerow(["BS 集計", label, "", calc.to_dollars(value), ""])
        writer.writerow([])
        writer.writerow(["指標", "値", "単位", "", ""])
        for label, value, unit in _kpi_rows(metrics, target):
            writer.writerow(["KPI", label, value, unit, ""])

        resp = make_response("﻿" + buf.getvalue())  # BOM 付きで Excel 対応
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = f"attachment; filename=enop_{month}.csv"
        return resp

    # ---- REST API ----------------------------------------------------------

    @app.get("/api/kpi")
    def api_kpi():
        conn = get_db()
        month = _month_arg()
        metrics = _kpi(conn, month)
        points = _trend(conn, month, app.config["TREND_MONTHS"])
        return jsonify(
            {
                "month": month,
                "currency": "USD",
                **_kpi_json(metrics),
                "trend": [
                    {
                        "month": p.month,
                        "revenue": calc.to_dollars(p.revenue),
                        "operating_income": calc.to_dollars(p.operating_income),
                        "net_income": calc.to_dollars(p.net_income),
                        "fl_ratio": p.fl_ratio,
                        "target_min": calc.to_dollars(p.target_min),
                        "achieved": p.achieved,
                    }
                    for p in points
                ],
                "trend_summary": {
                    **kpi.trend_summary(points),
                    "average_profit": calc.to_dollars(
                        kpi.trend_summary(points)["average_profit"]
                    ),
                },
            }
        )

    @app.get("/api/statements")
    def api_statements():
        conn = get_db()
        month = _month_arg()
        return jsonify(_statements_json(_statements(conn, month), month))

    @app.post("/api/entries")
    def api_add_entry():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            entry = _entry_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        entry_id = db.add_entry(conn, month, *entry)
        category, item, amount, memo = entry
        return jsonify(
            {
                "id": entry_id,
                "month": month,
                "category": category,
                "item": item,
                "amount": calc.to_dollars(amount),
                "memo": memo or "",
            }
        ), 201

    @app.delete("/api/entries/<int:entry_id>")
    def api_delete_entry(entry_id: int):
        conn = get_db()
        if db.get_entry(conn, entry_id) is None:
            return jsonify({"error": "明細が見つかりません。"}), 404
        db.delete_entry(conn, entry_id)
        return jsonify({"deleted": entry_id})

    @app.put("/api/target")
    def api_set_target():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            low = calc.parse_amount(data.get("target_min"))
            high = calc.parse_amount(data.get("target_max"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        db.set_target(conn, month, min(low, high), max(low, high))
        return jsonify(
            {
                "month": month,
                "target_min": calc.to_dollars(min(low, high)),
                "target_max": calc.to_dollars(max(low, high)),
            }
        )

    @app.put("/api/kpi-inputs")
    def api_set_kpi_inputs():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            customers, open_days, cash = _kpi_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        db.set_inputs(conn, month, customers, open_days, cash)
        return jsonify(
            {
                "month": month,
                "customers": customers,
                "open_days": open_days,
                "cash_balance": None if cash is None else calc.to_dollars(cash),
            }
        )

    @app.post("/api/import/payroll")
    def api_import_payroll():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            result = _import_payroll(conn, month, str(data.get("csv") or ""))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(
            {
                "month": month,
                "employees": result["employees"],
                "total_yen": result["total_yen"],
                "amount": calc.to_dollars(result["amount"]),
                "jpy_per_usd": app.config["JPY_PER_USD"],
            }
        ), 201

    # ---- 内部ヘルパー ------------------------------------------------------

    def _month_arg(value: str | None = None) -> str:
        """対象月('YYYY-MM')を解決する。不正な値は当月にフォールバック。"""
        month = value or request.args.get("month") or ""
        if not calc.is_valid_month(month):
            month = date.today().strftime("%Y-%m")
        return month

    def _entry_input(source) -> tuple[str, str, int, str | None]:
        """フォーム / JSON から明細の入力値を取り出して検証する。"""
        category = calc.validate_category(str(source.get("category") or "").strip())
        item = str(source.get("item") or "").strip()
        if not item:
            raise ValueError("科目名を入力してください。")
        amount = calc.parse_amount(source.get("amount"))
        memo = str(source.get("memo") or "").strip() or None
        return category, item, amount, memo

    def _kpi_input(source) -> tuple[int, int, int | None]:
        """客数・営業日数・現金残高の入力値を取り出して検証する。"""
        customers = _parse_int(source.get("customers"))
        open_days = _parse_int(source.get("open_days"))
        if open_days > 31:
            raise ValueError("営業日数は 31 日以内で入力してください。")
        raw_cash = source.get("cash_balance")
        cash = None
        if raw_cash not in (None, ""):
            cash = calc.parse_amount(raw_cash)
        return customers, open_days, cash

    def _target_range(conn, month: str) -> tuple[int, int]:
        """対象月の目標利益(セント)。月別設定が無ければ既定値を使う。"""
        row = db.get_target(conn, month)
        if row is None:
            return app.config["TARGET_MIN"], app.config["TARGET_MAX"]
        return row["target_min"], row["target_max"]

    def _statements(conn, month: str) -> dict:
        """対象月の PL・BS・目標達成状況を組み立てる。"""
        entries = db.list_entries(conn, month)
        pl = calc.compute_pl([e for e in entries if e.statement == "pl"], month)
        bs = calc.compute_bs([e for e in entries if e.statement == "bs"], month)
        target_min, target_max = _target_range(conn, month)
        basis = app.config["TARGET_BASIS"]
        target = calc.evaluate_target(pl.profit(basis), target_min, target_max, basis)
        return {"pl": pl, "bs": bs, "target": target}

    def _kpi(conn, month: str) -> kpi.Kpi:
        data = _statements(conn, month)
        return kpi.build_kpi(
            month, data["pl"], data["bs"], data["target"], db.get_inputs(conn, month)
        )

    def _trend(conn, month: str, count: int) -> list[kpi.TrendPoint]:
        """対象月を最後尾とする直近 count か月の推移。

        開店前などデータが無い月が先頭に並ぶとグラフが読みにくいので、
        最初に実績が現れる月より前は落とす。
        """
        months = [calc.month_shift(month, -offset) for offset in range(count - 1, -1, -1)]
        rows = []
        for target_month in months:
            data = _statements(conn, target_month)
            pl = data["pl"]
            if not rows and pl.is_empty:
                continue
            rows.append((target_month, pl, data["target"]))
        if not rows:
            data = _statements(conn, month)
            rows.append((month, data["pl"], data["target"]))
        return kpi.build_trend(rows)

    def _import_payroll(conn, month: str, text: str) -> dict:
        """給与 CSV を人件費として取り込む(同じ月の取り込み分は入れ替え)。"""
        result = payroll_import.parse_payroll_csv(text)
        amount = calc.yen_to_cents(result.total_yen, app.config["JPY_PER_USD"])
        db.delete_entries_by_source(conn, month, calc.SOURCE_IMPORT)
        db.add_entry(
            conn,
            month,
            "labor",
            "人件費(給与 CSV 取り込み)",
            amount,
            f"{result.employees} 名 / ¥{result.total_yen:,} ÷ "
            f"{app.config['JPY_PER_USD']:g} 円/$",
            source=calc.SOURCE_IMPORT,
        )
        return {
            "employees": result.employees,
            "total_yen": result.total_yen,
            "amount": amount,
        }

    def _statements_json(data: dict, month: str) -> dict:
        pl, bs, target = data["pl"], data["bs"], data["target"]
        usd = calc.to_dollars
        return {
            "month": month,
            "currency": "USD",
            "pl": {
                "sections": _sections_json(pl.sections),
                "totals": {key: usd(value) for key, _label, value in _pl_totals(pl)},
                "margins": {
                    "gross": pl.gross_margin,
                    "operating": pl.operating_margin,
                    "net": pl.net_margin,
                },
            },
            "bs": {
                "sections": _sections_json(bs.sections),
                "totals": {key: usd(value) for key, _label, value in _bs_totals(bs)},
                "balanced": bs.balanced,
                "equity_ratio": bs.equity_ratio,
                "current_ratio": bs.current_ratio,
            },
            "target": _target_json(target),
        }

    return app


# ---- モジュールレベルのヘルパー --------------------------------------------

def _target_json(target) -> dict:
    usd = calc.to_dollars
    return {
        "basis": target.basis,
        "profit": usd(target.profit),
        "target_min": usd(target.target_min),
        "target_max": usd(target.target_max),
        "status": target.status,
        "label": target.label,
        "achieved": target.achieved,
        "gap_to_min": usd(target.gap_to_min),
        "achievement_rate": target.achievement_rate,
        "annual_run_rate": usd(target.annual_run_rate),
    }


def _kpi_json(metrics) -> dict:
    usd = calc.to_dollars
    return {
        "target": _target_json(metrics.target),
        "sales": {
            "revenue": usd(metrics.revenue),
            "customers": metrics.customers,
            "average_spend": _opt_usd(metrics.average_spend),
            "daily_sales": _opt_usd(metrics.daily_sales),
            "daily_customers": metrics.daily_customers,
            "open_days": metrics.inputs.open_days,
        },
        "cost_ratios": {
            "food_ratio": metrics.food_ratio,
            "labor_ratio": metrics.labor_ratio,
            "fl_ratio": metrics.fl_ratio,
            "fl_level": metrics.fl_level,
            "opex_ratio": metrics.rent_ratio,
        },
        "cash": {
            "cash_balance": usd(metrics.cash),
            "estimated": metrics.cash_is_estimated,
            "monthly_burn": usd(metrics.monthly_burn),
            "runway_months": metrics.runway_months,
            "breakeven_revenue": _opt_usd(metrics.breakeven_revenue),
            "revenue_needed_for_target": _opt_usd(metrics.needed_revenue),
            "revenue_gap": usd(metrics.revenue_gap),
            "needed_daily_sales": _opt_usd(metrics.needed_daily_sales),
            "needed_customers": metrics.needed_customers,
        },
    }


def _kpi_rows(metrics, target) -> list[tuple[str, object, str]]:
    """CSV 出力用に主要指標を並べる。"""
    return [
        (f"{target.basis_label}", calc.to_dollars(target.profit), "USD"),
        ("目標達成率", target.achievement_rate, "%"),
        ("目標までの不足額", calc.to_dollars(target.gap_to_min), "USD"),
        ("売上高", calc.to_dollars(metrics.revenue), "USD"),
        ("客数", metrics.customers, "人"),
        ("客単価", _opt_usd(metrics.average_spend), "USD"),
        ("日商", _opt_usd(metrics.daily_sales), "USD"),
        ("原価率(F)", metrics.food_ratio, "%"),
        ("人件費率(L)", metrics.labor_ratio, "%"),
        ("FL 比率", metrics.fl_ratio, "%"),
        ("現金残高", calc.to_dollars(metrics.cash), "USD"),
        ("損益分岐点売上", _opt_usd(metrics.breakeven_revenue), "USD"),
        ("目標達成に必要な売上", _opt_usd(metrics.needed_revenue), "USD"),
        ("ランウェイ", metrics.runway_months, "か月"),
    ]


def _pl_totals(pl) -> list[tuple[str, str, int]]:
    """PL の集計値を (キー, ラベル, 金額) で返す。"""
    return [
        ("revenue", "売上高", pl.revenue),
        ("cogs", "売上原価", pl.cogs),
        ("gross_profit", "売上総利益", pl.gross_profit),
        ("labor_cost", "人件費", pl.labor_cost),
        ("opex", "その他販管費", pl.opex),
        ("operating_income", "営業利益", pl.operating_income),
        ("other_income", "営業外収益", pl.other_income),
        ("other_expense", "営業外費用", pl.other_expense),
        ("ordinary_income", "経常利益", pl.ordinary_income),
        ("tax", "法人税等", pl.tax),
        ("net_income", "当期純利益", pl.net_income),
    ]


def _bs_totals(bs) -> list[tuple[str, str, int]]:
    """BS の集計値を (キー, ラベル, 金額) で返す。"""
    return [
        ("current_assets", "流動資産", bs.current_assets),
        ("fixed_assets", "固定資産", bs.fixed_assets),
        ("total_assets", "資産合計", bs.total_assets),
        ("current_liabilities", "流動負債", bs.current_liabilities),
        ("long_liabilities", "固定負債", bs.long_liabilities),
        ("total_liabilities", "負債合計", bs.total_liabilities),
        ("total_equity", "純資産合計", bs.total_equity),
        ("total_liabilities_and_equity", "負債・純資産合計",
         bs.total_liabilities_and_equity),
        ("working_capital", "運転資本", bs.working_capital),
        ("difference", "貸借差額", bs.difference),
    ]


def _sections_json(sections) -> list[dict]:
    return [
        {
            "category": section.category,
            "label": section.label,
            "total": calc.to_dollars(section.total),
            "lines": [
                {
                    "id": line.id,
                    "item": line.item,
                    "amount": calc.to_dollars(line.amount),
                    "memo": line.memo,
                    "source": line.source,
                }
                for line in section.lines
            ],
        }
        for section in sections.values()
    ]


def _opt_usd(value: int | None) -> float | None:
    return None if value is None else calc.to_dollars(value)


def _env_cents(name: str, default: int) -> int:
    """環境変数のドル金額をセントに変換する。未設定・不正なら既定値。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return calc.parse_amount(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """環境変数を float として読む。未設定・不正・0 以下なら既定値。"""
    try:
        value = float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
