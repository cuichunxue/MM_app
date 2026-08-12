#!/usr/bin/env bash
# 初回セットアップ: venv作成・依存インストール・.env雛形の配置
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "→ venv を作成します (.venv)"
  python3 -m venv .venv
fi

echo "→ 依存パッケージをインストールします"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "→ .env を作成します(.env.example からコピー)"
  cp .env.example .env
  echo "  ADMIN_PASSWORD 等を必要に応じて編集してください: $(pwd)/.env"
fi

echo "→ セットアップ完了。起動するには: ./scripts/run.sh"
