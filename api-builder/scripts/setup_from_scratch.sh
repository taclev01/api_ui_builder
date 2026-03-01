#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/api_builder}"
MOCK_API_BASE_URL="${MOCK_API_BASE_URL:-http://localhost:8010}"
FORCE_NEW_VERSION="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database-url)
      DATABASE_URL="$2"
      shift 2
      ;;
    --mock-api-base-url)
      MOCK_API_BASE_URL="$2"
      shift 2
      ;;
    --force-new-version)
      FORCE_NEW_VERSION="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--database-url URL] [--mock-api-base-url URL] [--force-new-version]"
      exit 1
      ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing required command: uv"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Missing required command: npm"
  exit 1
fi

echo "[setup] Installing Python dependencies via uv sync..."
uv sync

echo "[setup] Installing frontend dependencies via npm ci..."
npm ci

BOOTSTRAP_ARGS=(
  "--database-url" "$DATABASE_URL"
  "--mock-api-base-url" "$MOCK_API_BASE_URL"
)

if [[ "$FORCE_NEW_VERSION" == "true" ]]; then
  BOOTSTRAP_ARGS+=("--force-new-version")
fi

echo "[setup] Applying migrations and seeding example workflow..."
uv run python backend/scripts/bootstrap_from_scratch.py "${BOOTSTRAP_ARGS[@]}"

echo ""
echo "[done] Setup complete."
echo "Start services in separate terminals:"
echo "  uv run uvicorn backend.app.main:app --reload --port 8000"
echo "  uv run uvicorn mock_api.app.main:app --reload --port 8010"
echo "  npm run dev"
