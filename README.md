# タイムカードシステム 🕒

社員の出退勤・休憩を記録し、勤務時間や残業を自動集計するシンプルなタイムカードシステムです。
Python (Flask) + SQLite で動作し、Web 画面と REST API の両方を備えています。

## 主な機能

- **打刻** — 出勤 / 退勤 / 休憩開始 / 休憩終了。状態遷移を検証し、不正な打刻(未出勤での退勤など)は拒否します。
- **会社 Wi-Fi 制限** — 打刻は会社ネットワーク(許可 IP / CIDR)からのみ可能。社外からの打刻はブロックします。
- **リアルタイム表示** — 打刻画面に社員ごとの現在の状態(未出勤 / 勤務中 / 休憩中)と本日の実働時間を表示。
- **月次集計** — 社員ごとに日別の実働・休憩・残業時間を集計。中抜け(1 日複数回の出退勤)にも対応。
- **残業計算** — 所定労働時間(既定 8 時間/日)を超えた分を自動的に残業として算出。
- **一括管理・給与計算** — 管理画面で全社員の月次勤怠・給与を一覧表示。時給と残業割増から支給額を自動計算し、CSV 出力も可能。
- **PL・BS 管理** — エノップの月次損益計算書(PL)と貸借対照表(BS)をここで一元管理。
  営業利益を月次目標 **$30,000〜$50,000** と突き合わせ、達成率・不足額・必要売上を自動計算します。
- **REST API** — 打刻機や外部システムから利用できる JSON API。

## 会社 Wi-Fi のみで打刻できる仕組み

打刻はサーバーがリクエスト元 IP アドレスを確認し、**許可されたネットワークからのアクセスのみ**受け付けます。

- 社内 LAN にサーバーを置く場合 → LAN のサブネット(例 `192.168.10.0/24`)を許可
- クラウド運用の場合 → オフィスから出ていく固定グローバル IP(例 `203.0.113.5`)を許可

`TIMECARD_ALLOWED_NETWORKS` にカンマ区切りで設定します。未設定の場合は制限なし(どこからでも打刻可)で、画面に警告が表示されます。リバースプロキシ配下では `TIMECARD_TRUST_PROXY=1` を設定すると `X-Forwarded-For` の元 IP で判定します。

```bash
# 例: 社内 LAN と拠点の固定 IP からのみ打刻を許可
export TIMECARD_ALLOWED_NETWORKS="192.168.10.0/24,203.0.113.5"
python run.py
```

> 注: IP アドレスによる制限はサーバー側で打刻を管理する運用における標準的な手法です。社内 VPN 経由のアクセスなどは許可 IP に含まれれば通過します。より厳密な端末認証が必要な場合はクライアント証明書等との併用を検討してください。

## PL・BS(財務管理)

エノップの数字は `/finance` 画面で月ごとに管理します。今後の PL / BS はすべてここに入力し、
このシステム上で計算・確認します。

### 月次目標 $30,000〜$50,000

エノップ開店後の目標は **毎月の計上利益(既定は営業利益)$30,000〜$50,000**。
対象月の利益をこの目標帯と突き合わせ、次を自動で表示します。

| 指標 | 内容 |
|------|------|
| 判定 | 未達 / 目標達成(レンジ内)/ 目標超過 |
| 達成率 | 利益 ÷ 目標下限($30,000) |
| 不足額 | 目標下限まであといくら必要か |
| 年間換算 | その月の利益が 12 か月続いた場合の年間利益 |
| 損益分岐点売上 | 利益ゼロに必要な売上(固定費 ÷(1 - 変動費率)) |
| 目標達成に必要な売上 | (固定費 + 目標利益)÷(1 - 変動費率) |

固定費は「人件費 + その他販管費」、変動費率は「売上原価 ÷ 売上高」として計算します。
目標は月ごとに上書きでき(画面のフォーム / `PUT /api/finance/target`)、
既定値は環境変数 `ENOP_TARGET_MIN` / `ENOP_TARGET_MAX` で変更できます。

### 入力する科目

| 区分 | カテゴリ | 例 |
|------|----------|-----|
| PL | 売上高 / 売上原価 / 人件費 / その他販管費 / 営業外収益 / 営業外費用 / 法人税等 | フード売上、食材原価、家賃、支払利息 |
| BS | 流動資産 / 固定資産 / 流動負債 / 固定負債 / 純資産 | 現金預金、内装設備、買掛金、長期借入金、資本金 |

- 金額は **USD**、費用や負債もプラスの金額で入力します(区分で符号を判定)。
  内部ではセント単位の整数で保持するため、丸め誤差が出ません。
- 家賃など毎月同じ科目は「前月の明細を複製」ボタンでまとめてコピーできます。
- PL では **売上総利益 → 営業利益 → 経常利益 → 当期純利益** と各利益率、
  BS では **貸借差額・運転資本・流動比率・自己資本比率** を自動計算します。
  貸借が一致しない月は画面上部に差額を警告表示します。

### 給与計算との連携

人件費は打刻・給与計算(`/admin`)の結果を自動で取り込みます。給与は円建てのため、
`ENOP_JPY_PER_USD`(既定 150 円/$)でドルに換算した金額を PL の人件費行に計上します
(「自動連携」タグ付き)。取り込みを止める場合は `ENOP_LINK_PAYROLL=0` を設定し、
人件費を手入力してください。

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
| `TIMECARD_ALLOWED_NETWORKS` | (なし) | 打刻を許可するネットワーク。カンマ区切りの CIDR / IP |
| `TIMECARD_TRUST_PROXY` | `0` | `1` にするとプロキシの `X-Forwarded-For` で IP 判定 |
| `TIMECARD_OVERTIME_RATE` | `1.25` | 残業割増率 |
| `TIMECARD_SECRET` | `dev-timecard-secret` | セッション用シークレット(本番は必ず変更) |
| `ENOP_TARGET_MIN` | `30000` | 月次目標利益の下限(USD) |
| `ENOP_TARGET_MAX` | `50000` | 月次目標利益の上限(USD) |
| `ENOP_TARGET_BASIS` | `operating` | 目標判定に使う利益(`operating`=営業利益 / `net`=当期純利益) |
| `ENOP_JPY_PER_USD` | `150` | 給与(円)を PL の人件費(ドル)に換算するレート |
| `ENOP_LINK_PAYROLL` | `1` | `0` にすると給与計算を人件費に自動取り込みしない |

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
| `POST` | `/api/employees` | 社員登録 `{"code","name","hourly_wage"}` |
| `PATCH`| `/api/employees/<id>` | 時給変更 `{"hourly_wage"}` |
| `POST` | `/api/employees/<id>/punch` | 打刻 `{"punch_type"}` (`in`/`out`/`break_in`/`break_out`)。会社ネットワーク外は 403 |
| `GET`  | `/api/employees/<id>/summary?date=YYYY-MM-DD` | 指定日の勤怠集計 |
| `GET`  | `/api/payroll?month=YYYY-MM` | 全社員の月次給与レポート |
| `GET`  | `/api/finance?month=YYYY-MM` | 月次 PL・BS・目標達成状況 |
| `POST` | `/api/finance/entries` | 明細登録 `{"month","category","item","amount","memo"}` |
| `DELETE` | `/api/finance/entries/<id>` | 明細削除 |
| `PUT`  | `/api/finance/target` | 月次目標の変更 `{"month","target_min","target_max"}` |

画面: `/`(打刻)、`/employee/<id>`(社員別 月次勤怠・給与)、`/admin`(一括管理・給与計算)、`/admin/payroll.csv`(CSV 出力)、`/finance`(PL・BS 管理)、`/finance/report.csv`(PL・BS の CSV 出力)

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

# 売上を計上
curl -X POST localhost:5000/api/finance/entries \
     -H 'Content-Type: application/json' \
     -d '{"month":"2026-09","category":"revenue","item":"フード売上","amount":180000}'

# 月次 PL・BS と目標達成状況
curl 'localhost:5000/api/finance?month=2026-09'
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
│   ├── payroll.py          # 給与計算ロジック(DB 非依存の純粋関数)
│   ├── finance.py          # PL・BS / 目標利益の計算ロジック(DB 非依存の純粋関数)
│   ├── network.py          # 会社 Wi-Fi(許可 IP)判定ロジック
│   ├── db.py               # SQLite データアクセス層
│   ├── templates/          # HTML テンプレート
│   └── static/             # CSS / JavaScript
└── tests/                  # pytest によるテスト
```

## テスト

```bash
python -m pytest
```

勤怠計算・給与計算・PL / BS 計算・ネットワーク判定の各ロジックと、API / 画面をカバーする
106 件のテストが含まれています(`tests/test_attendance.py`, `test_payroll.py`,
`test_finance.py`, `test_finance_app.py`, `test_network.py`, `test_app.py`)。

## 設計上のポイント

- **計算ロジックの分離** — 勤務時間・残業の計算は `attendance.py` に純粋関数として実装。
  データベースや Web フレームワークに依存しないため、単体テストが容易です。
- **状態遷移の検証** — 直近の打刻から現在の状態を判定し、不正な打刻を防ぎます。
- **データ整合性** — 退勤打刻漏れなど区間が閉じていない場合は警告(`warnings`)として表示します。
- **金額はセントの整数で保持** — PL・BS の金額は浮動小数点を使わずセント単位の整数で扱い、
  集計時の丸め誤差を防ぎます(`finance.py`)。
