#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  jobs -p | xargs -r kill
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT/backend"
  uv run uvicorn teachx.main:app --app-dir src --host 127.0.0.1 --port 8010 --reload
) &

(
  cd "$ROOT/frontend"
  npm run dev
) &

wait
