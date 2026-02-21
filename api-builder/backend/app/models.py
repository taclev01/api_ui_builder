from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


ExecutionStatus = Literal["queued", "running", "paused", "completed", "failed", "aborted"]


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    created_by: str | None = None


class WorkflowVersionCreate(BaseModel):
    graph_json: dict[str, Any]
    is_published: bool = True
    created_by: str | None = None


class ExecutionCreate(BaseModel):
    workflow_version_id: UUID
    input_json: dict[str, Any] = Field(default_factory=dict)
    debug_mode: bool = False


class DebugCommand(BaseModel):
    action: Literal["resume", "step", "abort"]


class WorkflowOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_by: str | None
    created_at: datetime


class ExecutionOut(BaseModel):
    id: UUID
    workflow_version_id: UUID
    status: ExecutionStatus
    started_at: datetime | None
    finished_at: datetime | None
    debug_mode: bool
    current_node_id: str | None


class EventOut(BaseModel):
    id: int
    execution_id: UUID
    event_index: int
    event_type: str
    node_id: str | None
    edge_id: str | None
    payload: dict[str, Any]
    occurred_at: datetime
