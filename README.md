# タイムカードシステム 🕒

社員の出退勤・休憩を記録し、勤務時間や残業を自動集計するシンプルなタイムカードシステムです。
Python (Flask) + SQLite で動作し、Web 画面と REST API の両方を備えています。

## 主な機能

- **打刻** — 出勤 / 退勤 / 休憩開始 / 休憩終了。状態遷移を検証し、不正な打刻(未出勤での退勤など)は拒否します。
- **リアルタイム表示** — 打刻画面に社員ごとの現在の状態(未出勤 / 勤務中 / 休憩中)と本日の実働時間を表示。
- **月次集計** — 社員ごとに日別の実働・休憩・残業時間を集計。中抜け(1 日複数回の出退勤)にも対応。
- **残業計算** — 所定労働時間(既定 8 時間/日)を超えた分を自動的に残業として算出。
- **REST API** — 打刻機や外部システムから利用できる JSON API。

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# サーバー起動
python run.py
```

ブラウザで <http://127.0.0.1:5000> を開きます。

### 環境変数

| 変数 | 既定値 | 説明 |
|------|--------|------|
| `TIMECARD_DB` | `timecard.db` | SQLite データベースのパス |
| `HOST` | `127.0.0.1` | バインドするホスト |
| `PORT` | `5000` | ポート番号 |

## 使い方(Web UI)

1. トップ画面下部のフォームから社員(社員コード・氏名)を登録します。
2. 各社員カードのボタンで打刻します。状態に応じて押せるボタンが自動で切り替わります。
   - 未出勤 → **出勤**
   - 勤務中 → **休憩開始** / **退勤**
   - 休憩中 → **休憩終了**
3. 社員名をクリックすると、月次の勤怠集計と打刻履歴を確認できます。

## REST API

| メソッド | パス | 説明 |
|----------|------|------|
| `GET`  | `/api/employees` | 社員一覧と現在の状態 |
| `POST` | `/api/employees` | 社員登録 `{"code","name"}` |
| `POST` | `/api/employees/<id>/punch` | 打刻 `{"punch_type"}` (`in`/`out`/`break_in`/`break_out`) |
| `GET`  | `/api/employees/<id>/summary?date=YYYY-MM-DD` | 指定日の勤怠集計 |

### 例

```bash
# 社員登録
curl -X POST localhost:5000/api/employees \
     -H 'Content-Type: application/json' \
     -d '{"code":"E001","name":"山田太郎"}'

# 出勤打刻
curl -X POST localhost:5000/api/employees/1/punch \
     -H 'Content-Type: application/json' \
     -d '{"punch_type":"in"}'

# 本日の集計を取得
curl localhost:5000/api/employees/1/summary
```

## プロジェクト構成

```
.
├── run.py                  # 開発サーバー起動スクリプト
├── requirements.txt
├── timecard/
│   ├── __init__.py
│   ├── app.py              # Flask アプリ(画面 + API)
│   ├── attendance.py       # 勤怠計算ロジック(DB 非依存の純粋関数)
│   ├── db.py               # SQLite データアクセス層
│   ├── templates/          # HTML テンプレート
│   └── static/             # CSS / JavaScript
└── tests/                  # pytest によるテスト
```

## テスト

```bash
python -m pytest
```

勤怠計算ロジック(`tests/test_attendance.py`)と API/画面(`tests/test_app.py`)を
カバーする 24 件のテストが含まれています。

## 設計上のポイント

- **計算ロジックの分離** — 勤務時間・残業の計算は `attendance.py` に純粋関数として実装。
  データベースや Web フレームワークに依存しないため、単体テストが容易です。
- **状態遷移の検証** — 直近の打刻から現在の状態を判定し、不正な打刻を防ぎます。
- **データ整合性** — 退勤打刻漏れなど区間が閉じていない場合は警告(`warnings`)として表示します。
