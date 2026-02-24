from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from app import engine, repository as repo


@pytest.fixture
def postgres_connection() -> Any:
    testcontainers = pytest.importorskip("testcontainers.postgres")
    PostgresContainer = testcontainers.PostgresContainer

    try:
        container = PostgresContainer("postgres:16-alpine")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {exc}")

    try:
        container.start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {exc}")

    dsn = container.get_connection_url()
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        sql_root = Path(__file__).resolve().parents[1] / "sql"
        with conn.cursor() as cur:
            cur.execute((sql_root / "001_init.sql").read_text())
            cur.execute((sql_root / "003_workflow_version_metadata.sql").read_text())
        conn.commit()
        yield conn
    finally:
        conn.close()
        container.stop()


@pytest.mark.integration
@pytest.mark.postgres
def test_engine_run_persists_events_and_saved_output(
    postgres_connection: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = postgres_connection

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        return {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {"approved": True, "amount": 15, "path": kwargs["url"]},
            "url": kwargs["url"],
            "method": kwargs["method"],
            "duration_ms": 5,
        }

    monkeypatch.setattr(engine, "_http_request", fake_http_request)

    workflow = repo.create_workflow(conn, name="integration-flow", description="integration", created_by="pytest")
    graph = {
        "entry_node_id": "start",
        "nodes": [
            {
                "id": "start",
                "data": {
                    "nodeType": "start_request",
                    "label": "Start",
                    "config": {"method": "GET", "url": "http://mock.local/start"},
                },
            },
            {
                "id": "if1",
                "data": {"nodeType": "if", "label": "If", "config": {"expression": "last_response.body.approved == True"}},
            },
            {
                "id": "save",
                "data": {"nodeType": "save", "label": "Save", "config": {"key": "approved", "from": "last_response.body.approved"}},
            },
            {"id": "end", "data": {"nodeType": "end", "label": "End", "config": {}}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "if1", "data": {}},
            {"id": "e2", "source": "if1", "sourceHandle": "true", "target": "save", "data": {"condition": "true"}},
            {"id": "e3", "source": "if1", "sourceHandle": "false", "target": "end", "data": {"condition": "false"}},
            {"id": "e4", "source": "save", "target": "end", "data": {}},
        ],
    }

    version = repo.create_workflow_version(
        conn,
        workflow_id=workflow["id"],
        graph_json=graph,
        version_note="integration",
        version_tag="itest",
        is_published=True,
        created_by="pytest",
    )
    execution = repo.create_execution(
        conn,
        workflow_version_id=version["id"],
        input_json={"seed": "data"},
        debug_mode=False,
        parent_execution_id=None,
        trigger_type="manual",
        trigger_payload={},
        idempotency_key=f"itest-{uuid4()}",
        correlation_id="pytest-correlation",
    )

    engine.run_execution(
        conn,
        execution_id=execution["id"],
        workflow_version=version,
        input_json={"seed": "data"},
        correlation_id="pytest-correlation",
    )
    conn.commit()

    refreshed = repo.get_execution(conn, execution["id"])
    assert refreshed is not None
    assert refreshed["status"] == "completed"
    assert refreshed["final_context_json"]["nodes"]["if1"]["output"]["result"] is True

    events = repo.list_events(conn, execution["id"])
    event_types = [row["event_type"] for row in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_COMPLETED" in event_types

    with conn.cursor() as cur:
        cur.execute(
            "SELECT key, value_json FROM api.saved_outputs WHERE execution_id = %s ORDER BY id ASC",
            (execution["id"],),
        )
        saved_rows = cur.fetchall()
    assert len(saved_rows) == 1
    assert saved_rows[0]["key"] == "approved"
    assert saved_rows[0]["value_json"] is True
