"""カラー剤計算機の公開用サーバー。

計算機の画面 (`colormix/`) を配信しつつ、はじめて使う人の登録を受け取る。

環境変数:
    COLORMIX_DB              SQLite のパス(既定: colormix.db)
    COLORMIX_ADMIN_TOKEN     管理画面の合言葉。未設定だと管理画面は開けない
    COLORMIX_CONTACT         登録画面に出す問い合わせ先(任意)
    COLORMIX_ALLOWED_ORIGIN  別ドメインの画面から登録を受けるとき指定(任意)
    COLORMIX_RATE_LIMIT      1 IP あたり 1 時間の登録上限(既定: 20)
"""

from __future__ import annotations

import csv
import hmac
import io
import json
import os
import time
from collections import defaultdict, deque

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from . import db
from .validation import ValidationError, validate_registration

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "colormix")
RATE_WINDOW_SECONDS = 3600


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or os.environ.get("COLORMIX_DB", "colormix.db")
    app.config["ADMIN_TOKEN"] = os.environ.get("COLORMIX_ADMIN_TOKEN", "")
    app.config["CONTACT"] = os.environ.get("COLORMIX_CONTACT", "")
    app.config["ALLOWED_ORIGIN"] = os.environ.get("COLORMIX_ALLOWED_ORIGIN", "")
    app.config["RATE_LIMIT"] = int(os.environ.get("COLORMIX_RATE_LIMIT", "20"))

    db.init_db(app.config["DB_PATH"])

    # IP ごとの直近の登録時刻。プロセス内だけの簡易なスパム避け
    recent: dict[str, deque] = defaultdict(deque)

    def client_ip() -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def rate_limited(ip: str) -> bool:
        limit = app.config["RATE_LIMIT"]
        if limit <= 0:
            return False
        now = time.monotonic()
        hits = recent[ip]
        while hits and now - hits[0] > RATE_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return True
        hits.append(now)
        return False

    def with_cors(response: Response) -> Response:
        origin = app.config["ALLOWED_ORIGIN"]
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return response

    # ---------- 画面 ----------

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/config.js")
    def config_js():
        """公開サーバー用の設定を差し込む(静的ファイルの config.js は使わない)。"""
        config = {
            "register": {
                "mode": "api",
                "apiUrl": "/api/register",
                "contact": app.config["CONTACT"],
            }
        }
        body = "window.COLORMIX_CONFIG = %s;\n" % json.dumps(config, ensure_ascii=False)
        return Response(body, mimetype="application/javascript")

    @app.get("/<path:filename>")
    def assets(filename: str):
        # 生成物と管理用ファイルは配らない
        if filename in {"standalone.html", "build.js"} or filename.endswith(".test.js"):
            abort(404)
        return send_from_directory(STATIC_DIR, filename)

    # ---------- 登録 API ----------

    @app.route("/api/register", methods=["POST", "OPTIONS"])
    def register():
        if request.method == "OPTIONS":
            return with_cors(Response(status=204))

        if rate_limited(client_ip()):
            return with_cors(jsonify({"ok": False, "error": "rate_limited"})), 429

        try:
            record = validate_registration(request.get_json(silent=True))
        except ValidationError as error:
            return with_cors(jsonify({"ok": False, "error": error.code})), 400

        row, created = db.save_registration(app.config["DB_PATH"], record)
        response = jsonify({"ok": True, "created": created, "instagram": row["instagram"]})
        return with_cors(response), (201 if created else 200)

    # ---------- 管理画面 ----------

    def require_admin() -> None:
        token = app.config["ADMIN_TOKEN"]
        if not token:
            # 合言葉が未設定のまま個人情報を見せない
            abort(503, "COLORMIX_ADMIN_TOKEN を設定してください")
        given = request.headers.get("X-Admin-Token") or request.args.get("token", "")
        if not hmac.compare_digest(given, token):
            abort(404)

    @app.get("/admin")
    def admin():
        require_admin()
        path = app.config["DB_PATH"]
        return render_template(
            "admin.html",
            rows=db.list_registrations(path),
            counts=db.count_by_affiliation(path),
            token=request.args.get("token", ""),
        )

    @app.get("/admin/registrations.csv")
    def admin_csv():
        require_admin()
        rows = db.list_registrations(app.config["DB_PATH"])

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["instagram", "affiliation", "salon", "lang", "created_at", "updated_at"])
        for row in rows:
            writer.writerow(
                [
                    row["instagram"],
                    row["affiliation"],
                    row["salon"],
                    row["lang"],
                    row["created_at"],
                    row["updated_at"],
                ]
            )

        # Excel で開いても文字化けしないよう BOM を付ける
        body = "﻿" + buffer.getvalue()
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=registrations.csv"},
        )

    return app
