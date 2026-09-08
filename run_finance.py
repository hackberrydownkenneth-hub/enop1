"""財務・経営指標システムの開発用サーバー起動スクリプト。

    python run_finance.py

環境変数:
    ENOP_DB        SQLite ファイルパス(既定: enop_finance.db)
    HOST           バインドするホスト(既定: 127.0.0.1)
    FINANCE_PORT   ポート番号(既定: 5001。タイムカードの 5000 と分ける)
    ENOP_DEBUG     1 にすると開発用のデバッグモード(自動リロード)で起動
"""

import os

from enop_finance import create_app

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("FINANCE_PORT", "5001"))
    debug = os.environ.get("ENOP_DEBUG") == "1"
    app.run(host=host, port=port, debug=debug)
