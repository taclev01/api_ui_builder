# Backend (V1 Draft)

FastAPI + Postgres draft implementation for event-sourced workflow execution.

## Run

1. Create DB and apply schema:
   - `psql < backend/sql/001_init.sql`
   - If upgrading an existing DB: `psql < backend/sql/002_execution_lineage.sql`
   - If upgrading an existing DB: `psql < backend/sql/003_workflow_version_metadata.sql`
2. Set env vars:
   - `DATABASE_URL=postgresql://user:pass@localhost:5432/api_builder`
3. Start API:
   - `uvicorn app.main:app --reload --port 8000`

## Tests

1. Install test dependency:
   - `uv add -r backend/requirements-dev.txt`
2. Run fast unit tests:
   - `uv run pytest backend/tests -q`
3. Run only mock API integration tests:
   - `uv run pytest backend/tests -m integration -q`
4. Run real Postgres testcontainer tests (requires Docker):
   - `uv run pytest backend/tests -m postgres -q`

## Notes

- This is a first draft for POC architecture.
- Execution engine is intentionally minimal and synchronous.
- Event stream and snapshot tables are the core of replay/time-travel design.
- `invoke_workflow` node is supported with parent/child execution lineage.
- Save/load endpoints for editor integration:
  - `GET /workflows`
  - `POST /workflows`
  - `GET /workflows/{workflow_id}/versions`
  - `POST /workflows/{workflow_id}/versions`
  - `GET /workflow-versions/{workflow_version_id}`
