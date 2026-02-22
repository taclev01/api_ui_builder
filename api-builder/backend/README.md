# Backend (V1 Draft)

FastAPI + Postgres draft implementation for event-sourced workflow execution.

## Run

1. Create DB and apply schema:
   - `psql < backend/sql/001_init.sql`
   - If upgrading an existing DB: `psql < backend/sql/002_execution_lineage.sql`
2. Set env vars:
   - `DATABASE_URL=postgresql://user:pass@localhost:5432/api_builder`
3. Start API:
   - `uvicorn app.main:app --reload --port 8000`

## Notes

- This is a first draft for POC architecture.
- Execution engine is intentionally minimal and synchronous.
- Event stream and snapshot tables are the core of replay/time-travel design.
- `invoke_workflow` node is supported with parent/child execution lineage.
