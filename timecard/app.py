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

from . import attendance, db, network, payroll

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

    return app


_STATUS_LABELS = {
    attendance.STATUS_OFF: "未出勤",
    attendance.STATUS_WORKING: "勤務中",
    attendance.STATUS_ON_BREAK: "休憩中",
}


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
