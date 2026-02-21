from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection

from .config import settings
from . import repository as repo


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
    # v1 simple behavior: first outgoing edge wins unless later typed rules are introduced
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


def run_execution(conn: Connection, execution_id: UUID, workflow_version: dict[str, Any], input_json: dict[str, Any]) -> None:
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
        system={"execution_id": str(execution_id)},
    )

    repo.append_event(
        conn,
        execution_id=execution_id,
        event_type="RUN_STARTED",
        payload={"workflow_version_id": str(workflow_version["id"])},
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

        # Minimal v1 draft execution behavior. Detailed semantics per node type can be expanded.
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
                context.vars[var_name] = value
            context.nodes[current_node_id] = {"status": "success", "output": {var_name: value}}
        elif node_type in {"form_request", "python_request"}:
            context.nodes[current_node_id] = {
                "status": "success",
                "output": {
                    "simulated": True,
                    "request": node_config,
                    "result": {"status_code": 200, "body": {}},
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
        elif node_type in {"start", "auth", "delay", "raise_error"}:
            if node_type == "raise_error":
                raise RuntimeError(node_config.get("message", "raise_error node triggered"))
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

    # v1 draft: resume restarts from current cursor semantics owned by executions.current_node_id
    execution = repo.get_execution(conn, execution_id)
    if not execution:
        raise RuntimeError("Execution not found")

    input_json = {}
    run_execution(conn, execution_id, workflow_version, input_json)
