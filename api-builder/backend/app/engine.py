from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection

from . import repository as repo
from .config import settings


@dataclass
class ExecutionContext:
    vars: dict[str, Any]
    nodes: dict[str, dict[str, Any]]
    system: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "vars": self.vars,
            "nodes": self.nodes,
            "system": self.system,
        }


def _index_graph(graph: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges", []):
        outgoing.setdefault(edge["source"], []).append(edge)
    return nodes, outgoing


def _resolve_next_edge(node_id: str, outgoing: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    edges = outgoing.get(node_id, [])
    return edges[0] if edges else None


def _write_snapshot_if_needed(conn: Connection, execution_id: UUID, context: ExecutionContext) -> None:
    next_idx = repo.get_next_event_index(conn, execution_id)
    if next_idx > 0 and next_idx % settings.snapshot_interval == 0:
        repo.create_snapshot(
            conn,
            execution_id=execution_id,
            event_index=next_idx - 1,
            context_json=context.to_json(),
        )
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="SNAPSHOT_WRITTEN",
            payload={"event_index": next_idx - 1},
        )


def _resolve_workflow_version_for_invocation(
    conn: Connection,
    node_config: dict[str, Any],
) -> dict[str, Any]:
    target_workflow_version_id = node_config.get("targetWorkflowVersionId")
    target_workflow_id = node_config.get("targetWorkflowId")

    if isinstance(target_workflow_version_id, str) and target_workflow_version_id:
        version = repo.get_workflow_version(conn, UUID(target_workflow_version_id))
        if not version:
            raise RuntimeError("invoke_workflow target workflow version not found")
        return version

    if isinstance(target_workflow_id, str) and target_workflow_id:
        version = repo.get_latest_published_workflow_version(conn, UUID(target_workflow_id))
        if not version:
            raise RuntimeError("invoke_workflow target published workflow version not found")
        return version

    raise RuntimeError("invoke_workflow requires targetWorkflowVersionId or targetWorkflowId")


def run_execution(
    conn: Connection,
    execution_id: UUID,
    workflow_version: dict[str, Any],
    input_json: dict[str, Any],
    *,
    call_depth: int = 0,
    parent_execution_id: UUID | None = None,
    correlation_id: str | None = None,
) -> None:
    if call_depth > settings.max_call_depth:
        raise RuntimeError(f"Maximum workflow call depth exceeded: {settings.max_call_depth}")

    graph = workflow_version["graph_json"]
    nodes, outgoing = _index_graph(graph)
    current_node_id = graph.get("entry_node_id")

    if not current_node_id or current_node_id not in nodes:
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="NODE_FAILED",
            payload={"error": "Missing or invalid entry_node_id"},
        )
        repo.update_execution_status(conn, execution_id=execution_id, status="failed")
        return

    context = ExecutionContext(
        vars={"input": input_json},
        nodes={},
        system={
            "execution_id": str(execution_id),
            "call_depth": call_depth,
            "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
            "correlation_id": correlation_id,
        },
    )

    repo.append_event(
        conn,
        execution_id=execution_id,
        event_type="RUN_STARTED",
        payload={
            "workflow_version_id": str(workflow_version["id"]),
            "call_depth": call_depth,
            "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
            "correlation_id": correlation_id,
        },
    )

    while True:
        node = nodes[current_node_id]
        node_type = node.get("type")
        node_config = node.get("config", {})

        repo.update_execution_status(
            conn,
            execution_id=execution_id,
            status="running",
            current_node_id=current_node_id,
        )
        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="NODE_STARTED",
            node_id=current_node_id,
            payload={"node_type": node_type},
        )

        if node_type == "end":
            context.nodes[current_node_id] = {"status": "success", "output": {"ended": True}}
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="NODE_SUCCEEDED",
                node_id=current_node_id,
            )
            repo.append_event(conn, execution_id=execution_id, event_type="RUN_COMPLETED")
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="completed",
                current_node_id=current_node_id,
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        if node_type == "define_variable":
            var_name = node_config.get("name")
            value = node_config.get("value")
            if var_name:
                context.vars[str(var_name)] = value
            context.nodes[current_node_id] = {"status": "success", "output": {str(var_name): value}}
        elif node_type in {"form_request", "python_request", "start_request", "start_python"}:
            context.nodes[current_node_id] = {
                "status": "success",
                "output": {
                    "simulated": True,
                    "request": node_config,
                    "result": {"status_code": 200, "body": {}},
                },
            }
        elif node_type == "invoke_workflow":
            child_version = _resolve_workflow_version_for_invocation(conn, node_config)
            child_input = node_config.get("input", {})
            if not isinstance(child_input, dict):
                raise RuntimeError("invoke_workflow input must be a JSON object")

            child_correlation_id = correlation_id or str(execution_id)

            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="INVOKE_WORKFLOW_STARTED",
                node_id=current_node_id,
                payload={
                    "target_workflow_version_id": str(child_version["id"]),
                    "target_workflow_id": str(child_version["workflow_id"]),
                },
            )

            child_execution = repo.create_execution(
                conn,
                workflow_version_id=child_version["id"],
                input_json=child_input,
                debug_mode=False,
                parent_execution_id=execution_id,
                trigger_type="workflow",
                trigger_payload={
                    "invoked_by_execution_id": str(execution_id),
                    "invoked_by_node_id": current_node_id,
                    "call_depth": call_depth + 1,
                },
                idempotency_key=None,
                correlation_id=child_correlation_id,
            )

            run_execution(
                conn,
                execution_id=child_execution["id"],
                workflow_version=child_version,
                input_json=child_input,
                call_depth=call_depth + 1,
                parent_execution_id=execution_id,
                correlation_id=child_correlation_id,
            )

            child_status = repo.get_execution(conn, child_execution["id"])
            if not child_status or child_status["status"] != "completed":
                raise RuntimeError("invoke_workflow child execution did not complete successfully")

            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="INVOKE_WORKFLOW_SUCCEEDED",
                node_id=current_node_id,
                payload={
                    "child_execution_id": str(child_execution["id"]),
                    "child_workflow_version_id": str(child_version["id"]),
                },
            )

            context.nodes[current_node_id] = {
                "status": "success",
                "output": {
                    "child_execution_id": str(child_execution["id"]),
                    "child_workflow_version_id": str(child_version["id"]),
                },
            }
        elif node_type == "if":
            context.nodes[current_node_id] = {"status": "success", "output": {"evaluated": True}}
        elif node_type == "for_each_parallel":
            context.nodes[current_node_id] = {"status": "success", "output": {"fanout": "draft"}}
        elif node_type == "join":
            context.nodes[current_node_id] = {"status": "success", "output": {"merged": True}}
        elif node_type == "save":
            context.nodes[current_node_id] = {"status": "success", "output": {"saved": True}}
        elif node_type in {"start", "auth", "parameters", "delay", "raise_error"}:
            if node_type == "raise_error":
                raise RuntimeError(str(node_config.get("message", "raise_error node triggered")))
            context.nodes[current_node_id] = {"status": "success", "output": {}}
        else:
            raise RuntimeError(f"Unsupported node type: {node_type}")

        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="NODE_SUCCEEDED",
            node_id=current_node_id,
            payload={"node_type": node_type},
        )

        edge = _resolve_next_edge(current_node_id, outgoing)
        if edge is None:
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="RUN_COMPLETED",
                payload={"reason": "No outgoing edge"},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="completed",
                current_node_id=current_node_id,
                final_context_json=context.to_json(),
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        if edge.get("breakpoint"):
            repo.append_event(
                conn,
                execution_id=execution_id,
                event_type="BREAKPOINT_PAUSED",
                edge_id=edge.get("id"),
                payload={"source": edge.get("source"), "target": edge.get("target")},
            )
            repo.update_execution_status(
                conn,
                execution_id=execution_id,
                status="paused",
                current_node_id=current_node_id,
            )
            _write_snapshot_if_needed(conn, execution_id, context)
            return

        repo.append_event(
            conn,
            execution_id=execution_id,
            event_type="EDGE_TRAVERSED",
            edge_id=edge.get("id"),
            payload={"source": edge.get("source"), "target": edge.get("target")},
        )
        current_node_id = edge["target"]
        _write_snapshot_if_needed(conn, execution_id, context)


def continue_execution_from_pause(
    conn: Connection,
    execution_id: UUID,
    workflow_version: dict[str, Any],
    action: str,
) -> None:
    if action == "abort":
        repo.append_event(conn, execution_id=execution_id, event_type="RUN_ABORTED")
        repo.update_execution_status(conn, execution_id=execution_id, status="aborted")
        return

    repo.append_event(
        conn,
        execution_id=execution_id,
        event_type="RUN_RESUMED",
        payload={"mode": action},
    )

    execution = repo.get_execution(conn, execution_id)
    if not execution:
        raise RuntimeError("Execution not found")

    run_execution(
        conn,
        execution_id=execution_id,
        workflow_version=workflow_version,
        input_json={},
        parent_execution_id=execution.get("parent_execution_id"),
        correlation_id=execution.get("correlation_id"),
    )
