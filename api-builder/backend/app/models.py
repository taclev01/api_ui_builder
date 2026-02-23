from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


ExecutionStatus = Literal["queued", "running", "paused", "completed", "failed", "aborted"]


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    created_by: str | None = None


class WorkflowVersionCreate(BaseModel):
    graph_json: dict[str, Any]
    version_note: str | None = None
    version_tag: str | None = None
    is_published: bool = True
    created_by: str | None = None


class ExecutionCreate(BaseModel):
    workflow_version_id: UUID | None = None
    workflow_id: UUID | None = None
    published_only: bool = True
    input_json: dict[str, Any] = Field(default_factory=dict)
    debug_mode: bool = False
    trigger_type: str | None = None
    trigger_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = None
    parent_execution_id: UUID | None = None

    @model_validator(mode="after")
    def validate_reference_mode(self) -> "ExecutionCreate":
        if (self.workflow_version_id is None) == (self.workflow_id is None):
            raise ValueError("Provide exactly one of workflow_version_id or workflow_id")
        return self


class DebugCommand(BaseModel):
    action: Literal["resume", "step", "abort"]


class WorkflowOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_by: str | None
    created_at: datetime


class WorkflowSummaryOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_by: str | None
    created_at: datetime
    latest_version_id: UUID | None
    latest_version_number: int | None
    latest_version_created_at: datetime | None
    latest_version_note: str | None
    latest_version_tag: str | None


class WorkflowVersionOut(BaseModel):
    id: UUID
    workflow_id: UUID
    version_number: int
    version_note: str | None
    version_tag: str | None
    is_published: bool
    created_by: str | None
    created_at: datetime


class WorkflowVersionDetailOut(BaseModel):
    id: UUID
    workflow_id: UUID
    version_number: int
    graph_json: dict[str, Any]
    version_note: str | None
    version_tag: str | None
    is_published: bool
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
    parent_execution_id: UUID | None
    trigger_type: str | None
    trigger_payload: dict[str, Any]
    idempotency_key: str | None
    correlation_id: str | None


class EventOut(BaseModel):
    id: int
    execution_id: UUID
    event_index: int
    event_type: str
    node_id: str | None
    edge_id: str | None
    payload: dict[str, Any]
    occurred_at: datetime
