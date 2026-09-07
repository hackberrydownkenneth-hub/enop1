"""タイムカードシステムの Flask アプリケーション。

打刻画面・社員別勤怠・管理画面(一括管理/給与計算)の Web UI と REST API を提供する。
打刻は会社ネットワーク(Wi-Fi)からのみ許可する。
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime

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

from . import attendance, db, finance, network, payroll

DEFAULT_DB = os.environ.get("TIMECARD_DB", "timecard.db")


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or DEFAULT_DB
    app.secret_key = os.environ.get("TIMECARD_SECRET", "dev-timecard-secret")

    # 打刻を許可するネットワーク(会社 Wi-Fi)の設定
    app.config["ALLOWED_NETWORKS"] = network.parse_networks(
        os.environ.get("TIMECARD_ALLOWED_NETWORKS")
    )
    app.config["TRUST_PROXY"] = os.environ.get("TIMECARD_TRUST_PROXY") == "1"
    # 残業割増率
    app.config["OVERTIME_RATE"] = float(
        os.environ.get("TIMECARD_OVERTIME_RATE", payroll.DEFAULT_OVERTIME_RATE)
    )

    # PL・BS(財務管理)の設定
    # 月次の目標利益。既定はエノップ開店後の目標 $30,000〜$50,000。
    app.config["TARGET_MIN"] = _env_cents("ENOP_TARGET_MIN", finance.TARGET_MIN)
    app.config["TARGET_MAX"] = _env_cents("ENOP_TARGET_MAX", finance.TARGET_MAX)
    # 目標を判定する利益(operating: 営業利益 / net: 当期純利益)
    basis = os.environ.get("ENOP_TARGET_BASIS", finance.DEFAULT_TARGET_BASIS)
    app.config["TARGET_BASIS"] = (
        basis if basis in (finance.BASIS_OPERATING, finance.BASIS_NET)
        else finance.DEFAULT_TARGET_BASIS
    )
    # 給与計算(円)を PL の人件費(ドル)に取り込む際の為替レート
    app.config["JPY_PER_USD"] = _env_float("ENOP_JPY_PER_USD", 150.0)
    app.config["LINK_PAYROLL"] = os.environ.get("ENOP_LINK_PAYROLL", "1") != "0"

    # テンプレートで金額を $1,234.56 形式に整形するフィルタ
    app.jinja_env.filters["usd"] = finance.format_usd

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

    # ---- ネットワーク制限ヘルパー -----------------------------------------

    def request_ip() -> str | None:
        return network.client_ip(
            request.remote_addr,
            request.headers.get("X-Forwarded-For"),
            app.config["TRUST_PROXY"],
        )

    def punch_allowed_here() -> bool:
        return network.is_allowed(request_ip(), app.config["ALLOWED_NETWORKS"])

    def restriction_enabled() -> bool:
        return bool(app.config["ALLOWED_NETWORKS"])

    # ---- 画面 --------------------------------------------------------------

    @app.route("/")
    def index() -> str:
        conn = get_db()
        employees = db.list_employees(conn)
        cards = []
        today = date.today().isoformat()
        for emp in employees:
            punches = db.get_punches(conn, emp["id"], date_prefix=today)
            status = attendance.compute_status(punches)
            summary = attendance.summarize_day(punches)
            cards.append(
                {
                    "employee": emp,
                    "status": status,
                    "status_label": _STATUS_LABELS[status],
                    "summary": summary,
                    "allowed": attendance.next_allowed_punches(status),
                }
            )
        return render_template(
            "index.html",
            cards=cards,
            today=today,
            restriction_enabled=restriction_enabled(),
            can_punch=punch_allowed_here(),
            client_ip=request_ip(),
        )

    @app.route("/employee/<int:employee_id>")
    def employee_detail(employee_id: int):
        conn = get_db()
        emp = db.get_employee(conn, employee_id)
        if emp is None:
            return render_template("error.html", message="社員が見つかりません。"), 404

        month = request.args.get("month") or date.today().strftime("%Y-%m")
        rows = db.get_punch_rows(conn, employee_id, date_prefix=month)
        days, totals = _summarize_month(rows)
        pay = payroll.compute_monthly_pay(
            [d["summary"] for d in days], emp["hourly_wage"], app.config["OVERTIME_RATE"]
        )

        return render_template(
            "employee.html",
            employee=emp,
            month=month,
            days=days,
            rows=rows,
            pay=pay,
        )

    @app.route("/admin")
    def admin():
        conn = get_db()
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        report = _payroll_report(conn, month)
        return render_template(
            "admin.html",
            month=month,
            report=report,
            grand_total=sum(r["pay"].total_pay for r in report),
            overtime_rate=app.config["OVERTIME_RATE"],
        )

    @app.route("/admin/payroll.csv")
    def admin_csv() -> Response:
        conn = get_db()
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        report = _payroll_report(conn, month)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["社員コード", "氏名", "出勤日数", "実労働時間", "残業時間",
             "時給", "基本給", "残業手当", "支給額合計"]
        )
        for r in report:
            emp, pay = r["employee"], r["pay"]
            writer.writerow(
                [emp["code"], emp["name"], pay.work_days, pay.work_hours,
                 pay.overtime_hours, pay.hourly_wage, pay.base_pay,
                 pay.overtime_pay, pay.total_pay]
            )

        resp = make_response("﻿" + buf.getvalue())  # BOM 付きで Excel 対応
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = (
            f"attachment; filename=payroll_{month}.csv"
        )
        return resp

    # ---- フォーム操作(Web UI 用) ----------------------------------------

    @app.route("/employees", methods=["POST"])
    def add_employee_form():
        conn = get_db()
        code = (request.form.get("code") or "").strip()
        name = (request.form.get("name") or "").strip()
        wage = _parse_int(request.form.get("hourly_wage"), default=0)
        if code and name:
            try:
                db.create_employee(conn, code, name, wage)
            except sqlite3.IntegrityError:
                flash("その社員コードは既に登録されています。", "error")
        return redirect(url_for("index"))

    @app.route("/employee/<int:employee_id>/wage", methods=["POST"])
    def update_wage_form(employee_id: int):
        wage = _parse_int(request.form.get("hourly_wage"), default=0)
        db.update_wage(get_db(), employee_id, wage)
        return redirect(request.referrer or url_for("admin"))

    @app.route("/employee/<int:employee_id>/delete", methods=["POST"])
    def delete_employee_form(employee_id: int):
        db.delete_employee(get_db(), employee_id)
        return redirect(url_for("index"))

    @app.route("/employee/<int:employee_id>/punch", methods=["POST"])
    def punch_form(employee_id: int):
        conn = get_db()
        if not punch_allowed_here():
            flash(
                "会社の Wi-Fi に接続しているときのみ打刻できます。"
                f"(接続元 IP: {request_ip()})",
                "error",
            )
            return redirect(url_for("index"))
        punch_type = request.form.get("punch_type", "")
        try:
            _do_punch(conn, employee_id, punch_type)
        except (ValueError, LookupError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("index"))

    # ---- PL・BS(財務管理) -----------------------------------------------

    @app.route("/finance")
    def finance_view():
        conn = get_db()
        month = _month_arg()
        data = _finance_data(conn, month)
        prev_month = finance.month_shift(month, -1)
        prev = _finance_data(conn, prev_month)
        return render_template(
            "finance.html",
            month=month,
            prev_month=prev_month,
            pl=data["pl"],
            bs=data["bs"],
            target=data["target"],
            prev_pl=prev["pl"],
            breakeven=finance.breakeven_revenue(data["pl"]),
            needed_revenue=finance.revenue_needed_for_target(
                data["pl"], data["target"].target_min
            ),
            pl_sections=finance.PL_SECTIONS,
            bs_sections=finance.BS_SECTIONS,
            asset_categories=finance.ASSET_CATEGORIES,
            liability_categories=finance.LIABILITY_CATEGORIES,
            category_labels=finance.CATEGORY_LABELS,
            months=db.list_fin_months(conn),
            jpy_per_usd=app.config["JPY_PER_USD"],
            link_payroll=app.config["LINK_PAYROLL"],
        )

    @app.route("/finance/entries", methods=["POST"])
    def add_fin_entry_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            entry = _entry_input(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.add_fin_entry(conn, month, *entry)
        return redirect(url_for("finance_view", month=month))

    @app.route("/finance/entries/<int:entry_id>/delete", methods=["POST"])
    def delete_fin_entry_form(entry_id: int):
        conn = get_db()
        row = db.get_fin_entry(conn, entry_id)
        month = _month_arg(row["month"] if row else request.form.get("month"))
        db.delete_fin_entry(conn, entry_id)
        return redirect(url_for("finance_view", month=month))

    @app.route("/finance/target", methods=["POST"])
    def set_fin_target_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        try:
            low = finance.parse_amount(request.form.get("target_min"))
            high = finance.parse_amount(request.form.get("target_max"))
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            db.set_fin_target(conn, month, min(low, high), max(low, high))
        return redirect(url_for("finance_view", month=month))

    @app.route("/finance/copy", methods=["POST"])
    def copy_fin_entries_form():
        conn = get_db()
        month = _month_arg(request.form.get("month"))
        source = _month_arg(request.form.get("from_month"))
        if source == month:
            flash("複製元と対象月が同じです。", "error")
            return redirect(url_for("finance_view", month=month))
        copied = db.copy_fin_entries(conn, source, month)
        if copied:
            flash(f"{source} の明細 {copied} 件を {month} に複製しました。", "info")
        else:
            flash(f"{source} には複製できる明細がありません。", "error")
        return redirect(url_for("finance_view", month=month))

    @app.route("/finance/report.csv")
    def finance_csv() -> Response:
        conn = get_db()
        month = _month_arg()
        data = _finance_data(conn, month)
        pl, bs, target = data["pl"], data["bs"], data["target"]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["対象月", month])
        writer.writerow([])
        writer.writerow(["区分", "カテゴリ", "科目", "金額(USD)", "備考"])
        for section in pl.sections.values():
            for line in section.lines:
                writer.writerow(
                    ["PL", section.label, line.item,
                     finance.to_dollars(line.amount), line.memo]
                )
        writer.writerow([])
        for _key, label, value in _pl_totals(pl):
            writer.writerow(["PL 集計", label, "", finance.to_dollars(value), ""])
        writer.writerow([])
        for section in bs.sections.values():
            for line in section.lines:
                writer.writerow(
                    ["BS", section.label, line.item,
                     finance.to_dollars(line.amount), line.memo]
                )
        writer.writerow([])
        for _key, label, value in _bs_totals(bs):
            writer.writerow(["BS 集計", label, "", finance.to_dollars(value), ""])
        writer.writerow([])
        writer.writerow(["目標", target.basis_label, target.label,
                         finance.to_dollars(target.profit), ""])
        writer.writerow(["目標下限", "", "", finance.to_dollars(target.target_min), ""])
        writer.writerow(["目標上限", "", "", finance.to_dollars(target.target_max), ""])

        resp = make_response("﻿" + buf.getvalue())  # BOM 付きで Excel 対応
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = f"attachment; filename=finance_{month}.csv"
        return resp

    # ---- REST API ----------------------------------------------------------

    @app.get("/api/employees")
    def api_list_employees():
        conn = get_db()
        result = []
        today = date.today().isoformat()
        for emp in db.list_employees(conn):
            punches = db.get_punches(conn, emp["id"], date_prefix=today)
            result.append(
                {
                    "id": emp["id"],
                    "code": emp["code"],
                    "name": emp["name"],
                    "hourly_wage": emp["hourly_wage"],
                    "status": attendance.compute_status(punches),
                }
            )
        return jsonify(result)

    @app.post("/api/employees")
    def api_create_employee():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip()
        name = (data.get("name") or "").strip()
        wage = _parse_int(data.get("hourly_wage"), default=0)
        if not code or not name:
            return jsonify({"error": "code と name は必須です。"}), 400
        try:
            emp_id = db.create_employee(conn, code, name, wage)
        except sqlite3.IntegrityError:
            return jsonify({"error": "その社員コードは既に存在します。"}), 409
        return jsonify({"id": emp_id, "code": code, "name": name, "hourly_wage": wage}), 201

    @app.patch("/api/employees/<int:employee_id>")
    def api_update_employee(employee_id: int):
        conn = get_db()
        if db.get_employee(conn, employee_id) is None:
            return jsonify({"error": "社員が見つかりません。"}), 404
        data = request.get_json(silent=True) or {}
        if "hourly_wage" in data:
            db.update_wage(conn, employee_id, _parse_int(data.get("hourly_wage"), 0))
        return jsonify({"id": employee_id, "hourly_wage": db.get_employee(conn, employee_id)["hourly_wage"]})

    @app.post("/api/employees/<int:employee_id>/punch")
    def api_punch(employee_id: int):
        conn = get_db()
        if not punch_allowed_here():
            return jsonify(
                {
                    "error": "会社の Wi-Fi に接続しているときのみ打刻できます。",
                    "client_ip": request_ip(),
                }
            ), 403
        data = request.get_json(silent=True) or {}
        punch_type = data.get("punch_type", "")
        try:
            punch_at = _do_punch(conn, employee_id, punch_type)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        punches = db.get_punches(conn, employee_id, date_prefix=date.today().isoformat())
        return jsonify(
            {
                "employee_id": employee_id,
                "punch_type": punch_type,
                "punched_at": punch_at.isoformat(timespec="seconds"),
                "status": attendance.compute_status(punches),
            }
        ), 201

    @app.get("/api/employees/<int:employee_id>/summary")
    def api_summary(employee_id: int):
        conn = get_db()
        emp = db.get_employee(conn, employee_id)
        if emp is None:
            return jsonify({"error": "社員が見つかりません。"}), 404
        target = request.args.get("date") or date.today().isoformat()
        punches = db.get_punches(conn, employee_id, date_prefix=target)
        summary = attendance.summarize_day(punches)
        return jsonify(
            {
                "employee_id": employee_id,
                "date": target,
                "status": attendance.compute_status(punches),
                "work_minutes": summary.work_minutes,
                "break_minutes": summary.break_minutes,
                "overtime_minutes": summary.overtime_minutes,
                "work_hours": summary.work_hours,
                "clock_in": summary.clock_in.isoformat() if summary.clock_in else None,
                "clock_out": summary.clock_out.isoformat() if summary.clock_out else None,
                "incomplete": summary.incomplete,
                "warnings": summary.warnings,
            }
        )

    @app.get("/api/payroll")
    def api_payroll():
        conn = get_db()
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        report = _payroll_report(conn, month)
        return jsonify(
            {
                "month": month,
                "overtime_rate": app.config["OVERTIME_RATE"],
                "employees": [
                    {
                        "id": r["employee"]["id"],
                        "code": r["employee"]["code"],
                        "name": r["employee"]["name"],
                        "work_days": r["pay"].work_days,
                        "work_hours": r["pay"].work_hours,
                        "overtime_hours": r["pay"].overtime_hours,
                        "hourly_wage": r["pay"].hourly_wage,
                        "base_pay": r["pay"].base_pay,
                        "overtime_pay": r["pay"].overtime_pay,
                        "total_pay": r["pay"].total_pay,
                        "has_incomplete": r["pay"].has_incomplete,
                    }
                    for r in report
                ],
                "grand_total": sum(r["pay"].total_pay for r in report),
            }
        )

    @app.get("/api/finance")
    def api_finance():
        conn = get_db()
        month = _month_arg()
        return jsonify(_finance_json(_finance_data(conn, month), month))

    @app.post("/api/finance/entries")
    def api_add_fin_entry():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            entry = _entry_input(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        entry_id = db.add_fin_entry(conn, month, *entry)
        category, item, amount, memo = entry
        return jsonify(
            {
                "id": entry_id,
                "month": month,
                "category": category,
                "item": item,
                "amount": finance.to_dollars(amount),
                "memo": memo or "",
            }
        ), 201

    @app.delete("/api/finance/entries/<int:entry_id>")
    def api_delete_fin_entry(entry_id: int):
        conn = get_db()
        if db.get_fin_entry(conn, entry_id) is None:
            return jsonify({"error": "明細が見つかりません。"}), 404
        db.delete_fin_entry(conn, entry_id)
        return jsonify({"deleted": entry_id})

    @app.put("/api/finance/target")
    def api_set_fin_target():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        month = _month_arg(data.get("month"))
        try:
            low = finance.parse_amount(data.get("target_min"))
            high = finance.parse_amount(data.get("target_max"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        db.set_fin_target(conn, month, min(low, high), max(low, high))
        return jsonify(
            {
                "month": month,
                "target_min": finance.to_dollars(min(low, high)),
                "target_max": finance.to_dollars(max(low, high)),
            }
        )

    # ---- 内部ヘルパー ------------------------------------------------------

    def _summarize_month(rows):
        """打刻行を日別に集計して (days, totals) を返す。"""
        by_day: dict[str, list[attendance.Punch]] = defaultdict(list)
        for r in rows:
            day = r["punched_at"][:10]
            by_day[day].append(
                attendance.Punch(
                    punch_type=r["punch_type"],
                    punched_at=datetime.fromisoformat(r["punched_at"]),
                )
            )
        days = []
        for day in sorted(by_day):
            days.append({"date": day, "summary": attendance.summarize_day(by_day[day])})
        return days, None

    def _payroll_report(conn, month):
        """全社員の月次給与レポートを作成する。"""
        report = []
        for emp in db.list_employees(conn):
            rows = db.get_punch_rows(conn, emp["id"], date_prefix=month)
            days, _ = _summarize_month(rows)
            pay = payroll.compute_monthly_pay(
                [d["summary"] for d in days],
                emp["hourly_wage"],
                app.config["OVERTIME_RATE"],
            )
            report.append({"employee": emp, "pay": pay})
        return report

    def _month_arg(value: str | None = None) -> str:
        """対象月('YYYY-MM')を解決する。不正な値は当月にフォールバック。"""
        month = value or request.args.get("month") or ""
        if not finance.is_valid_month(month):
            month = date.today().strftime("%Y-%m")
        return month

    def _entry_input(source) -> tuple[str, str, int, str | None]:
        """フォーム / JSON から明細の入力値を取り出して検証する。"""
        category = finance.validate_category(str(source.get("category") or "").strip())
        item = str(source.get("item") or "").strip()
        if not item:
            raise ValueError("科目名を入力してください。")
        amount = finance.parse_amount(source.get("amount"))
        memo = str(source.get("memo") or "").strip() or None
        return category, item, amount, memo

    def _fin_target(conn, month: str) -> tuple[int, int]:
        """対象月の目標利益(セント)。月別設定が無ければ既定値を使う。"""
        row = db.get_fin_target(conn, month)
        if row is None:
            return app.config["TARGET_MIN"], app.config["TARGET_MAX"]
        return row["target_min"], row["target_max"]

    def _payroll_labor_entry(conn, month: str) -> finance.Entry | None:
        """打刻・給与計算の結果を PL の人件費明細として取り込む。"""
        if not app.config["LINK_PAYROLL"]:
            return None
        total_yen = sum(r["pay"].total_pay for r in _payroll_report(conn, month))
        if total_yen <= 0:
            return None
        rate = app.config["JPY_PER_USD"]
        return finance.Entry(
            category="labor",
            item="人件費(タイムカード給与計算)",
            amount=finance.yen_to_cents(total_yen, rate),
            memo=f"¥{total_yen:,} ÷ {rate:g} 円/$",
            source=finance.SOURCE_TIMECARD,
        )

    def _finance_data(conn, month: str) -> dict:
        """対象月の PL・BS・目標達成状況をまとめて組み立てる。"""
        entries = db.list_fin_entries(conn, month)
        pl_entries = [e for e in entries if e.statement == "pl"]
        labor = _payroll_labor_entry(conn, month)
        if labor is not None:
            pl_entries.append(labor)
        pl = finance.compute_pl(pl_entries, month)
        bs = finance.compute_bs([e for e in entries if e.statement == "bs"], month)
        target_min, target_max = _fin_target(conn, month)
        basis = app.config["TARGET_BASIS"]
        target = finance.evaluate_target(
            pl.profit(basis), target_min, target_max, basis
        )
        return {"pl": pl, "bs": bs, "target": target}

    def _finance_json(data: dict, month: str) -> dict:
        pl, bs, target = data["pl"], data["bs"], data["target"]
        usd = finance.to_dollars
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
            "target": {
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
            },
            "breakeven_revenue": _opt_usd(finance.breakeven_revenue(pl)),
            "revenue_needed_for_target": _opt_usd(
                finance.revenue_needed_for_target(pl, target.target_min)
            ),
        }


    return app


_STATUS_LABELS = {
    attendance.STATUS_OFF: "未出勤",
    attendance.STATUS_WORKING: "勤務中",
    attendance.STATUS_ON_BREAK: "休憩中",
}


def _env_cents(name: str, default: int) -> int:
    """環境変数のドル金額をセントに変換する。未設定・不正なら既定値。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return finance.parse_amount(raw)
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


def _do_punch(conn: sqlite3.Connection, employee_id: int, punch_type: str) -> datetime:
    """状態遷移を検証したうえで打刻を記録し、打刻時刻を返す。"""
    if punch_type not in attendance.PUNCH_TYPES:
        raise ValueError(f"不正な打刻種別です: {punch_type!r}")
    emp = db.get_employee(conn, employee_id)
    if emp is None:
        raise LookupError("社員が見つかりません。")

    today = date.today().isoformat()
    punches = db.get_punches(conn, employee_id, date_prefix=today)
    status = attendance.compute_status(punches)
    attendance.validate_transition(status, punch_type)

    now = datetime.now().replace(microsecond=0)
    db.add_punch(conn, employee_id, punch_type, now)
    return now


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
            "total": finance.to_dollars(section.total),
            "lines": [
                {
                    "id": line.id,
                    "item": line.item,
                    "amount": finance.to_dollars(line.amount),
                    "memo": line.memo,
                    "source": line.source,
                }
                for line in section.lines
            ],
        }
        for section in sections.values()
    ]


def _opt_usd(value: int | None) -> float | None:
    return None if value is None else finance.to_dollars(value)
