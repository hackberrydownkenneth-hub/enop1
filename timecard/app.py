"""タイムカードシステムの Flask アプリケーション。

Web UI と REST API の両方を提供する。
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

from . import attendance, db

DEFAULT_DB = os.environ.get("TIMECARD_DB", "timecard.db")


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or DEFAULT_DB

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
        return render_template("index.html", cards=cards, today=today)

    @app.route("/employee/<int:employee_id>")
    def employee_detail(employee_id: int) -> str:
        conn = get_db()
        emp = db.get_employee(conn, employee_id)
        if emp is None:
            return render_template("error.html", message="社員が見つかりません。"), 404

        month = request.args.get("month") or date.today().strftime("%Y-%m")
        rows = db.get_punch_rows(conn, employee_id, date_prefix=month)

        # 日毎にグループ化して集計
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
        total_work = 0
        total_overtime = 0
        for day in sorted(by_day):
            summary = attendance.summarize_day(by_day[day])
            total_work += summary.work_minutes
            total_overtime += summary.overtime_minutes
            days.append({"date": day, "summary": summary})

        return render_template(
            "employee.html",
            employee=emp,
            month=month,
            days=days,
            rows=rows,
            total_work_hours=round(total_work / 60, 2),
            total_overtime_hours=round(total_overtime / 60, 2),
        )

    # ---- フォーム操作(Web UI 用) ----------------------------------------

    @app.route("/employees", methods=["POST"])
    def add_employee_form():
        conn = get_db()
        code = (request.form.get("code") or "").strip()
        name = (request.form.get("name") or "").strip()
        if code and name:
            try:
                db.create_employee(conn, code, name)
            except sqlite3.IntegrityError:
                pass  # 社員コード重複は無視
        return redirect(url_for("index"))

    @app.route("/employee/<int:employee_id>/delete", methods=["POST"])
    def delete_employee_form(employee_id: int):
        db.delete_employee(get_db(), employee_id)
        return redirect(url_for("index"))

    @app.route("/employee/<int:employee_id>/punch", methods=["POST"])
    def punch_form(employee_id: int):
        conn = get_db()
        punch_type = request.form.get("punch_type", "")
        _do_punch(conn, employee_id, punch_type)
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
        if not code or not name:
            return jsonify({"error": "code と name は必須です。"}), 400
        try:
            emp_id = db.create_employee(conn, code, name)
        except sqlite3.IntegrityError:
            return jsonify({"error": "その社員コードは既に存在します。"}), 409
        return jsonify({"id": emp_id, "code": code, "name": name}), 201

    @app.post("/api/employees/<int:employee_id>/punch")
    def api_punch(employee_id: int):
        conn = get_db()
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

    return app


_STATUS_LABELS = {
    attendance.STATUS_OFF: "未出勤",
    attendance.STATUS_WORKING: "勤務中",
    attendance.STATUS_ON_BREAK: "休憩中",
}


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
