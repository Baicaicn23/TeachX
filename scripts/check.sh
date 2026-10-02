#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

(
  cd "$ROOT/backend"
  uv run ruff check src tests
  # Local .env may point at a real provider. Automated checks must stay
  # deterministic and must never consume API credits.
  TEACHX_LLM_PROVIDER=mock \
    TEACHX_EMBEDDING_PROVIDER=mock \
    TEACHX_AUTH_ENABLED=false \
    uv run pytest -q
)

(
  cd "$ROOT/frontend"
  npm run typecheck
)
