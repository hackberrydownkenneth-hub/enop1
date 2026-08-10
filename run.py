"""開発用サーバーの起動スクリプト。

    python run.py

環境変数:
    TIMECARD_DB   SQLite ファイルパス(既定: timecard.db)
    HOST          バインドするホスト(既定: 127.0.0.1)
    PORT          ポート番号(既定: 5000)
"""

import os

from timecard import create_app

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
