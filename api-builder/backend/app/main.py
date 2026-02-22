from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException

from . import repository as repo
from .db import get_conn
from .engine import continue_execution_from_pause, run_execution
from .models import (
    DebugCommand,
    EventOut,
    ExecutionCreate,
    ExecutionOut,
    WorkflowCreate,
    WorkflowOut,
    WorkflowVersionCreate,
)

app = FastAPI(title="API Logic Builder Backend", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/workflows", response_model=WorkflowOut)
def create_workflow(payload: WorkflowCreate) -> Any:
    with get_conn() as conn:
        row = repo.create_workflow(
            conn,
            name=payload.name,
            description=payload.description,
            created_by=payload.created_by,
        )
        return row


@app.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: UUID) -> Any:
    with get_conn() as conn:
        row = repo.get_workflow(conn, workflow_id)
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return row


@app.post("/workflows/{workflow_id}/versions")
def create_workflow_version(workflow_id: UUID, payload: WorkflowVersionCreate) -> Any:
    with get_conn() as conn:
        workflow = repo.get_workflow(conn, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        version = repo.create_workflow_version(
            conn,
            workflow_id=workflow_id,
            graph_json=payload.graph_json,
            is_published=payload.is_published,
            created_by=payload.created_by,
        )
        return version


def _resolve_workflow_version_for_execution(conn: Any, payload: ExecutionCreate) -> dict[str, Any] | None:
    if payload.workflow_version_id:
        return repo.get_workflow_version(conn, payload.workflow_version_id)

    if payload.workflow_id:
        if payload.published_only:
            return repo.get_latest_published_workflow_version(conn, payload.workflow_id)

        # For v1, non-published mode still resolves to latest published for safety.
        return repo.get_latest_published_workflow_version(conn, payload.workflow_id)

    return None


@app.post("/executions", response_model=ExecutionOut)
def create_execution(payload: ExecutionCreate) -> Any:
    with get_conn() as conn:
        workflow_version = _resolve_workflow_version_for_execution(conn, payload)
        if not workflow_version:
            raise HTTPException(status_code=404, detail="Workflow version not found")

        if payload.idempotency_key:
            existing = repo.get_execution_by_idempotency_key(conn, payload.idempotency_key)
            if existing:
                return existing

        execution = repo.create_execution(
            conn,
            workflow_version_id=workflow_version["id"],
            input_json=payload.input_json,
            debug_mode=payload.debug_mode,
            parent_execution_id=payload.parent_execution_id,
            trigger_type=payload.trigger_type,
            trigger_payload=payload.trigger_payload,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
        )

        call_depth_raw = payload.trigger_payload.get("call_depth", 0)
        call_depth = call_depth_raw if isinstance(call_depth_raw, int) else 0

        try:
            run_execution(
                conn,
                execution_id=execution["id"],
                workflow_version=workflow_version,
                input_json=payload.input_json,
                call_depth=call_depth,
                parent_execution_id=payload.parent_execution_id,
                correlation_id=payload.correlation_id,
            )
        except Exception as exc:
            repo.append_event(
                conn,
                execution_id=execution["id"],
                event_type="NODE_FAILED",
                payload={"error": str(exc)},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution["id"],
                status="failed",
            )

        refreshed = repo.get_execution(conn, execution["id"])
        return refreshed


@app.get("/executions/{run_id}", response_model=ExecutionOut)
def get_execution(run_id: UUID) -> Any:
    with get_conn() as conn:
        execution = repo.get_execution(conn, run_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution


@app.get("/executions/{run_id}/events", response_model=list[EventOut])
def get_execution_events(run_id: UUID) -> list[dict[str, Any]]:
    with get_conn() as conn:
        execution = repo.get_execution(conn, run_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return repo.list_events(conn, run_id)


@app.get("/executions/{run_id}/state")
def get_execution_state(run_id: UUID, event_index: int) -> dict[str, Any]:
    with get_conn() as conn:
        execution = repo.get_execution(conn, run_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")

        snap = repo.get_latest_snapshot_before(conn, run_id, event_index)
        if not snap:
            return {"event_index": event_index, "context": None, "note": "No snapshot yet"}

        return {
            "event_index": event_index,
            "snapshot_event_index": snap["event_index"],
            "context": snap["context_json"],
        }


@app.post("/executions/{run_id}/debug/resume", response_model=ExecutionOut)
def debug_resume(run_id: UUID) -> Any:
    return _debug_command(run_id, DebugCommand(action="resume"))


@app.post("/executions/{run_id}/debug/step", response_model=ExecutionOut)
def debug_step(run_id: UUID) -> Any:
    return _debug_command(run_id, DebugCommand(action="step"))


@app.post("/executions/{run_id}/debug/abort", response_model=ExecutionOut)
def debug_abort(run_id: UUID) -> Any:
    return _debug_command(run_id, DebugCommand(action="abort"))


def _debug_command(run_id: UUID, cmd: DebugCommand) -> Any:
    with get_conn() as conn:
        execution = repo.get_execution(conn, run_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        if execution["status"] != "paused" and cmd.action != "abort":
            raise HTTPException(status_code=409, detail="Execution is not paused")

        workflow_version = repo.get_workflow_version(conn, execution["workflow_version_id"])
        if not workflow_version:
            raise HTTPException(status_code=404, detail="Workflow version not found")

        continue_execution_from_pause(
            conn,
            execution_id=run_id,
            workflow_version=workflow_version,
            action=cmd.action,
        )
        return repo.get_execution(conn, run_id)
