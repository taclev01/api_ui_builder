# Workflow Test REST API

Standalone FastAPI service for testing workflow nodes in the UI builder.

## Run

From `/Users/tonyclevenger/GitRepos/api_ui_builder/api-builder`:

```bash
uv run uvicorn mock_api.app.main:app --reload --port 8010
```

Open docs:

- `http://127.0.0.1:8010/docs`

## Endpoints to test node types

- `GET /users`: pagination (`page`, `page_size`) and filtering.
- `GET /orders`: pagination + response parsing (`status`, `min_amount`, etc.).
- `POST /logic/branch`: deterministic `if`-style decision payload.
- `GET /fanout/targets`: returns list for `for`/parallel fan-out.
- `GET /fanout/targets/{target_id}/detail`: request in parallel from each target.
- `POST /resilience/flaky?key=...&fail_until=...`: retry/circuit-break test.
- `GET /resilience/timeout?delay_ms=...`: timeout behavior.
- `GET /auth/check`: auth test.
  - `Authorization: Bearer demo-token` or `x-api-key: demo-key`
- `POST /echo`: validate request shaping and saved payloads.
- `GET /stats/summary`: simple aggregate response.

## Suggested quick workflow tests

1. Pagination loop:
   - `start_request -> form_request(/users?page=1) -> if(next_page) -> invoke/loop`
2. Fan-out:
   - `form_request(/fanout/targets) -> for(each target_id) -> form_request(/fanout/targets/{id}/detail) -> save`
3. Retry:
   - `form_request(/resilience/flaky?key=test-a&fail_until=2)` with retries enabled.
4. Branching:
   - `define_variable(amount)` -> `if` using `/logic/branch` output.
