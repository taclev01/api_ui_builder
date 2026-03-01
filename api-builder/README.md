# API UI Builder (POC)

TypeScript/React workflow editor (`reactflow`, `antd`, `codemirror`) with a FastAPI + Postgres backend execution engine.

## One-command local setup

From `/Users/tonyclevenger/GitRepos/api_ui_builder/api-builder`:

```bash
./scripts/setup_from_scratch.sh
```

Optional flags:

```bash
./scripts/setup_from_scratch.sh \
  --database-url "postgresql://postgres:postgres@localhost:5432/api_builder" \
  --mock-api-base-url "http://localhost:8010" \
  --force-new-version
```

This will:

- install Python dependencies via `uv sync`
- install frontend dependencies via `npm ci`
- create/apply DB schema migrations in `backend/sql`
- seed a runnable example workflow named `first workflow` (published)

## Run services

Use 3 terminals:

```bash
uv run uvicorn backend.app.main:app --reload --port 8000
uv run uvicorn mock_api.app.main:app --reload --port 8010
npm run dev
```

Frontend: [http://localhost:5173](http://localhost:5173)

## Seed-only script

If dependencies are already installed, run just DB bootstrap + seed:

```bash
uv run python backend/scripts/bootstrap_from_scratch.py
```

