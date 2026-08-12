#!/usr/bin/env bash
# 本番起動: .env を読み込み、venv の gunicorn で起動する
# 使い方: ./scripts/run.sh [BIND] [WORKERS] [THREADS]
#   例:   ./scripts/run.sh 0.0.0.0:8000 2 4
set -euo pipefail
cd "$(dirname "$0")/.."

BIND="${1:-0.0.0.0:8000}"
WORKERS="${2:-2}"
THREADS="${3:-4}"

if [ ! -x .venv/bin/gunicorn ]; then
  echo "venv が未セットアップです。先に ./scripts/setup.sh を実行してください" >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# SQLite は BEGIN IMMEDIATE + busy_timeout で書き込みを直列化しているため
# マルチワーカーでも安全。社内規模(〜数百人)なら 2 workers で十分
exec .venv/bin/gunicorn --bind "$BIND" --workers "$WORKERS" --threads "$THREADS" \
  --access-logfile - --error-logfile - \
  'backend:create_app()'
