"""カラー剤計算機の公開サーバーを起動する。

    python run_colormix.py

環境変数:
    COLORMIX_DB            SQLite ファイルパス(既定: colormix.db)
    COLORMIX_ADMIN_TOKEN   管理画面 /admin の合言葉(未設定だと管理画面は開けない)
    COLORMIX_CONTACT       登録画面に出す問い合わせ先(任意)
    HOST                   バインドするホスト(既定: 127.0.0.1)
    PORT                   ポート番号(既定: 5001)
"""

import os

from colormix_server import create_app

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))
    app.run(host=host, port=port, debug=True)
