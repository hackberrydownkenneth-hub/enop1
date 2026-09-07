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

from . import calc, chart, db, kpi, lifecycle, payroll_import

DEFAULT_DB = os.environ.get("ENOP_DB", "enop_finance.db")
DEFAULT_TREND_MONTHS = 12
DEFAULT_FORECAST_MONTHS = 6
# 累計を遡る上限(暴走防止)
MAX_HISTORY_MONTHS = 120


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
    # 給与 CSV の金額を HK$ に換算するレート(HK$1 あたりの元通貨額。
    # 給与も HK$ 建てなら 1.0 のままでよい)
    app.config["PAYROLL_RATE"] = _env_float("ENOP_PAYROLL_RATE", 1.0)
    # ダッシュボードに表示する推移の月数
    app.config["TREND_MONTHS"] = int(
        _env_float("ENOP_TREND_MONTHS", DEFAULT_TREND_MONTHS)
    )
    # 累計・回収の予測で先まで伸ばす月数
    app.config["FORECAST_MONTHS"] = int(
        _env_float("ENOP_FORECAST_MONTHS", DEFAULT_FORECAST_MONTHS)
    )
    # 投資余力の計算で手元に残す運転資金の月数
    app.config["RESERVE_MONTHS"] = int(
        _env_float("ENOP_RESERVE_MONTHS", lifecycle.DEFAULT_RESERVE_MONTHS)
    )

    # テンプレートで金額を HK$1,234.56 形式に整形するフィルタ
    app.jinja_env.filters["money"] = calc.format_money

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
        cycle = _lifecycle(conn, month)
        return render_template(
            "dashboard.html",
            month=month,
            kpi=metrics,
            prev=prev,
            target=metrics.target,
            payback=cycle["cycle"].payback,
            investment=cycle["investment"],
            capacity=cycle["cycle"].capacity,
            cycle_finish=next(
                (s.finish_month for s in cycle["cycle"].scenarios if s.finish_month), None
            ),
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

    @app.route("/lifecycle")
    def lifecycle_view():
        conn = get_db()
        month = _month_arg()
        data = _lifecycle(conn, month)
        points = data["cycle"].points
        return render_template(
            "lifecycle.html",
            month=month,
            cycle=data["cycle"],
            payback=data["cycle"].payback,
            costs=data["costs"],
            investment=data["investment"],
            position_chart=chart.bar_chart(
                [(p.month[2:], p.position) for p in points],
                forecast_from=len(data["cycle"].history),
            ),
            forecast_months=app.config["FORECAST_MONTHS"],
            months=db.list_months(conn),
        )

    @app.route("/startup-costs", methods=["POST"])
    def add_startup_cost_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            item, amount, cost_month, memo = _cost_input(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.add_startup_cost(conn, item, amount, cost_month, memo)
        return redirect(url_for("lifecycle_view", month=month))

    @app.route("/startup-costs/<int:cost_id>/delete", methods=["POST"])
    def delete_startup_cost_form(cost_id: int):
        conn = get_db()
        db.delete_startup_cost(conn, cost_id)
        return redirect(url_for("lifecycle_view", month=_month_arg(request.form.get("month"))))

    @app.route("/plans", methods=["POST"])
    def add_plan_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            name, amount, memo = _plan_input(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.add_plan(conn, name, amount, memo)
        return redirect(url_for("lifecycle_view", month=month))

    @app.route("/plans/<int:plan_id>/delete", methods=["POST"])
    def delete_plan_form(plan_id: int):
        conn = get_db()
        db.delete_plan(conn, plan_id)
        return redirect(url_for("lifecycle_view", month=_month_arg(request.form.get("month"))))

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
            payroll_rate=app.config["PAYROLL_RATE"],
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
                f"{result['employees']} 名分の給与を "
                f"人件費 {calc.format_money(result['amount'])} として取り込みました。",
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
        writer.writerow(["区分", "カテゴリ", "科目", f"金額({calc.CURRENCY_CODE})", "備考"])
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
                "currency": calc.CURRENCY_CODE,
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

    @app.get("/api/lifecycle")
    def api_lifecycle():
        conn = get_db()
        month = _month_arg()
        return jsonify(_lifecycle_json(_lifecycle(conn, month), month))

    @app.post("/api/startup-costs")
    def api_add_startup_cost():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        try:
            item, amount, cost_month, memo = _cost_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        cost_id = db.add_startup_cost(conn, item, amount, cost_month, memo)
        return jsonify(
            {
                "id": cost_id,
                "item": item,
                "amount": calc.to_dollars(amount),
                "month": cost_month,
                "memo": memo or "",
            }
        ), 201

    @app.delete("/api/startup-costs/<int:cost_id>")
    def api_delete_startup_cost(cost_id: int):
        conn = get_db()
        if db.get_startup_cost(conn, cost_id) is None:
            return jsonify({"error": "オープンコストが見つかりません。"}), 404
        db.delete_startup_cost(conn, cost_id)
        return jsonify({"deleted": cost_id})

    @app.post("/api/plans")
    def api_add_plan():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        try:
            name, amount, memo = _plan_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        plan_id = db.add_plan(conn, name, amount, memo)
        return jsonify(
            {"id": plan_id, "name": name, "amount": calc.to_dollars(amount), "memo": memo or ""}
        ), 201

    @app.delete("/api/plans/<int:plan_id>")
    def api_delete_plan(plan_id: int):
        conn = get_db()
        if db.get_plan(conn, plan_id) is None:
            return jsonify({"error": "計画が見つかりません。"}), 404
        db.delete_plan(conn, plan_id)
        return jsonify({"deleted": plan_id})

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
                "total_amount": result["total_amount"],
                "amount": calc.to_dollars(result["amount"]),
                "payroll_rate": app.config["PAYROLL_RATE"],
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
        amount = calc.to_hkd_cents(result.total_amount, app.config["PAYROLL_RATE"])
        db.delete_entries_by_source(conn, month, calc.SOURCE_IMPORT)
        db.add_entry(
            conn,
            month,
            "labor",
            "人件費(給与 CSV 取り込み)",
            amount,
            _import_memo(result, app.config["PAYROLL_RATE"]),
            source=calc.SOURCE_IMPORT,
        )
        return {
            "employees": result.employees,
            "total_amount": result.total_amount,
            "amount": amount,
        }

    def _cost_input(source) -> tuple[str, int, str | None, str | None]:
        """オープンコストの入力値を取り出して検証する。"""
        item = str(source.get("item") or "").strip()
        if not item:
            raise ValueError("項目名を入力してください。")
        amount = calc.parse_amount(source.get("amount"))
        raw_month = str(source.get("cost_month") or "").strip()
        cost_month = raw_month if calc.is_valid_month(raw_month) else None
        memo = str(source.get("memo") or "").strip() or None
        return item, amount, cost_month, memo

    def _plan_input(source) -> tuple[str, int, str | None]:
        """「次にやれること」の入力値を取り出して検証する。"""
        name = str(source.get("name") or "").strip()
        if not name:
            raise ValueError("やりたいことの名前を入力してください。")
        amount = calc.parse_amount(source.get("amount"))
        memo = str(source.get("memo") or "").strip() or None
        return name, amount, memo

    def _history(conn, month: str) -> list[lifecycle.MonthResult]:
        """データがある最初の月から対象月までの月次実績。"""
        recorded = [m for m in db.list_months(conn) if m <= month]
        if not recorded:
            return []
        start = min(recorded)
        basis = app.config["TARGET_BASIS"]
        results = []
        cursor = start
        for _ in range(MAX_HISTORY_MONTHS):
            data = _statements(conn, cursor)
            pl = data["pl"]
            results.append(
                lifecycle.MonthResult(
                    month=cursor,
                    revenue=pl.revenue,
                    profit=pl.profit(basis),
                    net_income=pl.net_income,
                )
            )
            if cursor >= month:
                break
            cursor = calc.month_shift(cursor, 1)
        return results

    def _lifecycle(conn, month: str) -> dict:
        """開店からの累計・回収・予測・投資余力をまとめる。"""
        months = _history(conn, month)
        investment = db.total_startup_cost(conn)
        payback = lifecycle.evaluate_payback(months, investment)
        target_min, target_max = _target_range(conn, month)
        metrics = _kpi(conn, month)

        capacity = lifecycle.investment_capacity(
            metrics.cash,
            calc.fixed_cost(metrics.pl),
            app.config["RESERVE_MONTHS"],
        )
        plans = lifecycle.evaluate_plans(
            [(row["id"], row["name"], row["amount"], row["memo"] or "")
             for row in db.list_plans(conn)],
            capacity,
            payback.recent_average_profit,
            payback.last_month or month,
        )
        cycle = lifecycle.Lifecycle(
            payback=payback,
            history=lifecycle.build_history(
                [m for m in months if m.has_activity], investment
            ),
            forecast=lifecycle.project(
                payback,
                payback.recent_average_profit,
                app.config["FORECAST_MONTHS"],
            ),
            scenarios=lifecycle.forecast_scenarios(payback, target_min, target_max),
            capacity=capacity,
            plans=plans,
        )
        return {
            "cycle": cycle,
            "investment": investment,
            "costs": db.list_startup_costs(conn),
        }

    def _lifecycle_json(data: dict, month: str) -> dict:
        cycle = data["cycle"]
        payback = cycle.payback
        usd = calc.to_dollars
        return {
            "month": month,
            "currency": calc.CURRENCY_CODE,
            "investment": usd(data["investment"]),
            "payback": {
                "phase": payback.phase,
                "phase_label": payback.phase_label,
                "cumulative_profit": usd(payback.cumulative_profit),
                "cumulative_net_income": usd(payback.cumulative_net_income),
                "position": usd(payback.position),
                "recovered": payback.recovered,
                "remaining": usd(payback.remaining),
                "recovery_rate": payback.recovery_rate,
                "surplus": usd(payback.surplus),
                "months_elapsed": payback.months_elapsed,
                "profitable_months": payback.profitable_months,
                "first_profitable_month": payback.first_profitable_month,
                "payback_month": payback.payback_month,
                "worst_position": usd(payback.worst_position),
                "worst_month": payback.worst_month,
                "average_profit": usd(payback.average_profit),
                "recent_average_profit": usd(payback.recent_average_profit),
            },
            "history": [_point_json(p) for p in cycle.history],
            "forecast": [_point_json(p) for p in cycle.forecast],
            "scenarios": [
                {
                    "key": s.key,
                    "label": s.label,
                    "monthly_profit": usd(s.monthly_profit),
                    "months_needed": s.months_needed,
                    "finish_month": s.finish_month,
                }
                for s in cycle.scenarios
            ],
            "capacity": {
                "cash": usd(cycle.capacity.cash),
                "monthly_fixed_cost": usd(cycle.capacity.monthly_fixed_cost),
                "reserve_months": cycle.capacity.reserve_months,
                "reserve_needed": usd(cycle.capacity.reserve_needed),
                "available": usd(cycle.capacity.available),
            },
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "amount": usd(p.amount),
                    "memo": p.memo,
                    "funded": p.funded,
                    "shortfall": usd(p.shortfall),
                    "progress": p.progress,
                    "months_needed": p.months_needed,
                    "ready_month": p.ready_month,
                }
                for p in cycle.plans
            ],
        }

    def _statements_json(data: dict, month: str) -> dict:
        pl, bs, target = data["pl"], data["bs"], data["target"]
        usd = calc.to_dollars
        return {
            "month": month,
            "currency": calc.CURRENCY_CODE,
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

def _point_json(point) -> dict:
    usd = calc.to_dollars
    return {
        "month": point.month,
        "revenue": usd(point.revenue),
        "profit": usd(point.profit),
        "net_income": usd(point.net_income),
        "cumulative_profit": usd(point.cumulative_profit),
        "position": usd(point.position),
        "remaining": usd(point.remaining),
        "recovery_rate": point.recovery_rate,
        "forecast": point.forecast,
    }


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
        (f"{target.basis_label}", calc.to_dollars(target.profit), calc.CURRENCY_CODE),
        ("目標達成率", target.achievement_rate, "%"),
        ("目標までの不足額", calc.to_dollars(target.gap_to_min), calc.CURRENCY_CODE),
        ("売上高", calc.to_dollars(metrics.revenue), calc.CURRENCY_CODE),
        ("客数", metrics.customers, "人"),
        ("客単価", _opt_usd(metrics.average_spend), calc.CURRENCY_CODE),
        ("日商", _opt_usd(metrics.daily_sales), calc.CURRENCY_CODE),
        ("原価率(F)", metrics.food_ratio, "%"),
        ("人件費率(L)", metrics.labor_ratio, "%"),
        ("FL 比率", metrics.fl_ratio, "%"),
        ("現金残高", calc.to_dollars(metrics.cash), calc.CURRENCY_CODE),
        ("損益分岐点売上", _opt_usd(metrics.breakeven_revenue), calc.CURRENCY_CODE),
        ("目標達成に必要な売上", _opt_usd(metrics.needed_revenue), calc.CURRENCY_CODE),
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


def _import_memo(result, rate: float) -> str:
    """給与取り込み明細の備考。"""
    base = f"{result.employees} 名分の給与 CSV"
    if rate == 1.0:
        return f"{base}(合計 {calc.format_money(result.total_amount * 100)})"
    return f"{base}(合計 {result.total_amount:,} ÷ {rate:g} = HK$ 換算)"


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
