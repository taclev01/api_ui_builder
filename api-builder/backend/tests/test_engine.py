from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib import parse
from uuid import UUID, uuid4

import pytest

from app import engine


@dataclass
class RepoState:
    events: list[dict[str, Any]] = field(default_factory=list)
    executions: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    saved_outputs: list[dict[str, Any]] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    workflow_versions: dict[UUID, dict[str, Any]] = field(default_factory=dict)


@pytest.fixture
def repo_state(monkeypatch: pytest.MonkeyPatch) -> RepoState:
    state = RepoState()

    def get_next_event_index(_conn: Any, execution_id: UUID) -> int:
        return len([event for event in state.events if event["execution_id"] == execution_id])

    def append_event(
        _conn: Any,
        *,
        execution_id: UUID,
        event_type: str,
        node_id: str | None = None,
        edge_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": len(state.events) + 1,
            "execution_id": execution_id,
            "event_index": get_next_event_index(_conn, execution_id),
            "event_type": event_type,
            "node_id": node_id,
            "edge_id": edge_id,
            "payload": payload or {},
            "occurred_at": datetime.now(UTC),
        }
        state.events.append(event)
        return event

    def update_execution_status(
        _conn: Any,
        *,
        execution_id: UUID,
        status: str,
        current_node_id: str | None = None,
        final_context_json: dict[str, Any] | None = None,
    ) -> None:
        current = state.executions.get(
            execution_id,
            {
                "id": execution_id,
                "status": "running",
                "current_node_id": None,
                "final_context_json": None,
                "parent_execution_id": None,
                "correlation_id": None,
                "workflow_version_id": uuid4(),
            },
        )
        current["status"] = status
        current["current_node_id"] = current_node_id
        if final_context_json is not None:
            current["final_context_json"] = final_context_json
        state.executions[execution_id] = current

    def create_snapshot(
        _conn: Any,
        *,
        execution_id: UUID,
        event_index: int,
        context_json: dict[str, Any],
    ) -> None:
        state.snapshots.append(
            {
                "execution_id": execution_id,
                "event_index": event_index,
                "context_json": context_json,
            }
        )

    def create_saved_output(
        _conn: Any,
        *,
        execution_id: UUID,
        key: str,
        value_json: Any,
    ) -> dict[str, Any]:
        row = {
            "id": len(state.saved_outputs) + 1,
            "execution_id": execution_id,
            "key": key,
            "value_json": value_json,
            "created_at": datetime.now(UTC),
        }
        state.saved_outputs.append(row)
        return row

    def get_execution(_conn: Any, execution_id: UUID) -> dict[str, Any] | None:
        return state.executions.get(execution_id)

    def create_execution(
        _conn: Any,
        *,
        workflow_version_id: UUID,
        input_json: dict[str, Any],
        debug_mode: bool,
        parent_execution_id: UUID | None,
        trigger_type: str | None,
        trigger_payload: dict[str, Any],
        idempotency_key: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        execution_id = uuid4()
        row = {
            "id": execution_id,
            "workflow_version_id": workflow_version_id,
            "status": "running",
            "debug_mode": debug_mode,
            "current_node_id": None,
            "final_context_json": None,
            "parent_execution_id": parent_execution_id,
            "trigger_type": trigger_type,
            "trigger_payload": trigger_payload,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        }
        state.executions[execution_id] = row
        return row

    def get_workflow_version(_conn: Any, workflow_version_id: UUID) -> dict[str, Any] | None:
        return state.workflow_versions.get(workflow_version_id)

    def get_latest_published_workflow_version(_conn: Any, workflow_id: UUID) -> dict[str, Any] | None:
        for row in state.workflow_versions.values():
            if row["workflow_id"] == workflow_id and row.get("is_published"):
                return row
        return None

    def get_latest_workflow_version(_conn: Any, workflow_id: UUID) -> dict[str, Any] | None:
        for row in state.workflow_versions.values():
            if row["workflow_id"] == workflow_id:
                return row
        return None

    monkeypatch.setattr(engine.repo, "get_next_event_index", get_next_event_index)
    monkeypatch.setattr(engine.repo, "append_event", append_event)
    monkeypatch.setattr(engine.repo, "update_execution_status", update_execution_status)
    monkeypatch.setattr(engine.repo, "create_snapshot", create_snapshot)
    monkeypatch.setattr(engine.repo, "create_saved_output", create_saved_output)
    monkeypatch.setattr(engine.repo, "get_execution", get_execution)
    monkeypatch.setattr(engine.repo, "create_execution", create_execution)
    monkeypatch.setattr(engine.repo, "get_workflow_version", get_workflow_version)
    monkeypatch.setattr(engine.repo, "get_latest_published_workflow_version", get_latest_published_workflow_version)
    monkeypatch.setattr(engine.repo, "get_latest_workflow_version", get_latest_workflow_version)
    return state


def _workflow(graph: dict[str, Any], *, workflow_id: UUID | None = None) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "workflow_id": workflow_id or uuid4(),
        "version_number": 1,
        "graph_json": graph,
        "is_published": True,
    }


def test_if_branch_and_save_output(repo_state: RepoState, monkeypatch: pytest.MonkeyPatch) -> None:
    execution_id = uuid4()
    calls = {"count": 0}

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        return {
            "status_code": 200,
            "headers": {},
            "body": {"approved": True, "amount": 80},
            "url": kwargs["url"],
            "method": kwargs["method"],
            "duration_ms": 10,
        }

    monkeypatch.setattr(engine, "_http_request", fake_http_request)

    graph = {
        "entry_node_id": "start",
        "nodes": [
            {
                "id": "start",
                "data": {
                    "nodeType": "start_request",
                    "label": "Start Request",
                    "config": {"method": "GET", "url": "http://example.test/start"},
                },
            },
            {
                "id": "if1",
                "data": {
                    "nodeType": "if",
                    "label": "Gate",
                    "config": {"expression": "last_response.body.approved == True"},
                },
            },
            {
                "id": "save1",
                "data": {
                    "nodeType": "save",
                    "label": "Save Result",
                    "config": {"key": "approved", "from": "last_response.body.approved"},
                },
            },
            {"id": "end1", "data": {"nodeType": "end", "label": "End", "config": {}}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "if1", "data": {}},
            {"id": "e2", "source": "if1", "sourceHandle": "true", "target": "save1", "data": {"condition": "true"}},
            {"id": "e3", "source": "if1", "sourceHandle": "false", "target": "end1", "data": {"condition": "false"}},
            {"id": "e4", "source": "save1", "target": "end1", "data": {}},
        ],
    }

    workflow_version = _workflow(graph)
    engine.run_execution(
        conn=None,  # type: ignore[arg-type]
        execution_id=execution_id,
        workflow_version=workflow_version,
        input_json={"token": "abc"},
    )

    execution = repo_state.executions[execution_id]
    assert execution["status"] == "completed"
    assert calls["count"] == 1
    assert repo_state.saved_outputs[0]["key"] == "approved"
    assert repo_state.saved_outputs[0]["value_json"] is True
    context = execution["final_context_json"]
    assert context["nodes"]["if1"]["output"]["result"] is True


def test_breakpoint_pause_then_resume(repo_state: RepoState, monkeypatch: pytest.MonkeyPatch) -> None:
    execution_id = uuid4()
    calls = {"count": 0}

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        return {
            "status_code": 200,
            "headers": {},
            "body": {"ok": True},
            "url": kwargs["url"],
            "method": kwargs["method"],
            "duration_ms": 8,
        }

    monkeypatch.setattr(engine, "_http_request", fake_http_request)

    graph = {
        "entry_node_id": "start",
        "nodes": [
            {
                "id": "start",
                "data": {"nodeType": "start_request", "label": "Start", "config": {"method": "GET", "url": "http://x"}},
            },
            {"id": "end", "data": {"nodeType": "end", "label": "End", "config": {}}},
        ],
        "edges": [
            {"id": "bp", "source": "start", "target": "end", "data": {"breakpoint": True}},
        ],
    }
    workflow_version = _workflow(graph)

    engine.run_execution(
        conn=None,  # type: ignore[arg-type]
        execution_id=execution_id,
        workflow_version=workflow_version,
        input_json={},
    )
    paused = repo_state.executions[execution_id]
    assert paused["status"] == "paused"
    assert paused["current_node_id"] == "end"
    assert calls["count"] == 1

    engine.continue_execution_from_pause(
        conn=None,  # type: ignore[arg-type]
        execution_id=execution_id,
        workflow_version=workflow_version,
        action="resume",
    )
    resumed = repo_state.executions[execution_id]
    assert resumed["status"] == "completed"
    assert calls["count"] == 1
    assert any(event["event_type"] == "BREAKPOINT_PAUSED" for event in repo_state.events)
    assert any(event["event_type"] == "RUN_RESUMED" for event in repo_state.events)


def test_paginate_request_page_number_strategy(repo_state: RepoState, monkeypatch: pytest.MonkeyPatch) -> None:
    execution_id = uuid4()

    def fake_http_request(**kwargs: Any) -> dict[str, Any]:
        parsed = parse.urlparse(kwargs["url"])
        query = dict(parse.parse_qsl(parsed.query))
        page = int(query.get("page", "1"))
        has_more = page < 3
        return {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {"data": [f"item-{page}-a", f"item-{page}-b"], "has_more": has_more},
            "url": kwargs["url"],
            "method": kwargs["method"],
            "duration_ms": 12,
        }

    monkeypatch.setattr(engine, "_http_request", fake_http_request)

    graph = {
        "entry_node_id": "page",
        "nodes": [
            {
                "id": "page",
                "data": {
                    "nodeType": "paginate_request",
                    "label": "Paginate",
                    "config": {
                        "method": "GET",
                        "url": "http://api.local/users",
                        "strategy": "page_number",
                        "itemsPath": "body.data",
                        "hasMorePath": "body.has_more",
                        "maxPages": 10,
                        "pageSize": 2,
                    },
                },
            },
            {"id": "end", "data": {"nodeType": "end", "label": "End", "config": {}}},
        ],
        "edges": [{"id": "e1", "source": "page", "target": "end", "data": {}}],
    }
    workflow_version = _workflow(graph)

    engine.run_execution(
        conn=None,  # type: ignore[arg-type]
        execution_id=execution_id,
        workflow_version=workflow_version,
        input_json={},
    )

    execution = repo_state.executions[execution_id]
    assert execution["status"] == "completed"
    output = execution["final_context_json"]["nodes"]["page"]["output"]
    assert output["pages_fetched"] == 3
    assert len(output["items"]) == 6
