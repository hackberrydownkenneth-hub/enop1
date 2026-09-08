#!/usr/bin/env bash
# タイムカード(打刻・勤怠・給与)を起動する。
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.10 以上が必要です。https://www.python.org/downloads/ からインストールしてください。"
  read -r -p "Enter キーで終了します..." _ || true
  exit 1
fi

if [ ! -d .venv ]; then
  echo "初回セットアップ中(1 分ほどかかります)..."
  "$PYTHON" -m venv .venv
fi
# 依存がそろっていれば再インストールしない(2 回目以降はすぐ起動する)
if ! ./.venv/bin/python -c "import flask" >/dev/null 2>&1; then
  echo "必要なライブラリをインストールしています..."
  if ! ./.venv/bin/python -m pip install --quiet -r requirements.txt; then
    echo
    echo "ライブラリのインストールに失敗しました。ネットワーク接続を確認して、もう一度実行してください。"
    read -r -p "Enter キーで終了します..." _ || true
    exit 1
  fi
fi

PORT="${PORT:-5000}"
URL="http://127.0.0.1:${PORT}"
echo
echo "  タイムカードを起動しました → ${URL}"
echo "  終了するには このウィンドウで Ctrl+C を押してください。"
echo
( sleep 2; (open "$URL" || xdg-open "$URL") >/dev/null 2>&1 || true ) &
exec ./.venv/bin/python run.py
