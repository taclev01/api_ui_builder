from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection


def create_workflow(
    conn: Connection,
    *,
    name: str,
    description: str | None,
    created_by: str | None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflows(name, description, created_by)
            VALUES (%s, %s, %s)
            RETURNING id, name, description, created_by, created_at
            """,
            (name, description, created_by),
        )
        return cur.fetchone()


def create_workflow_version(
    conn: Connection,
    *,
    workflow_id: UUID,
    graph_json: dict[str, Any],
    is_published: bool,
    created_by: str | None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM workflow_versions WHERE workflow_id = %s",
            (workflow_id,),
        )
        next_version = cur.fetchone()["next_version"]

        cur.execute(
            """
            INSERT INTO workflow_versions(workflow_id, version_number, graph_json, is_published, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, workflow_id, version_number, graph_json, is_published, created_by, created_at
            """,
            (workflow_id, next_version, graph_json, is_published, created_by),
        )
        return cur.fetchone()


def get_workflow(conn: Connection, workflow_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, created_by, created_at FROM workflows WHERE id = %s",
            (workflow_id,),
        )
        return cur.fetchone()


def create_execution(
    conn: Connection,
    *,
    workflow_version_id: UUID,
    input_json: dict[str, Any],
    debug_mode: bool,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO executions(workflow_version_id, status, started_at, debug_mode, input_json)
            VALUES (%s, 'running', now(), %s, %s)
            RETURNING id, workflow_version_id, status, started_at, finished_at, debug_mode, current_node_id
            """,
            (workflow_version_id, debug_mode, input_json),
        )
        return cur.fetchone()


def get_execution(conn: Connection, execution_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_version_id, status, started_at, finished_at, debug_mode, current_node_id
            FROM executions
            WHERE id = %s
            """,
            (execution_id,),
        )
        return cur.fetchone()


def get_workflow_version(conn: Connection, workflow_version_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, workflow_id, version_number, graph_json FROM workflow_versions WHERE id = %s",
            (workflow_version_id,),
        )
        return cur.fetchone()


def get_next_event_index(conn: Connection, execution_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(event_index), -1) + 1 AS next_idx FROM execution_events WHERE execution_id = %s",
            (execution_id,),
        )
        row = cur.fetchone()
        return int(row["next_idx"])


def append_event(
    conn: Connection,
    *,
    execution_id: UUID,
    event_type: str,
    node_id: str | None = None,
    edge_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    event_index = get_next_event_index(conn, execution_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO execution_events(execution_id, event_index, event_type, node_id, edge_id, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, execution_id, event_index, event_type, node_id, edge_id, payload, occurred_at
            """,
            (execution_id, event_index, event_type, node_id, edge_id, payload),
        )
        return cur.fetchone()


def update_execution_status(
    conn: Connection,
    *,
    execution_id: UUID,
    status: str,
    current_node_id: str | None = None,
    final_context_json: dict[str, Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        if status in {"completed", "failed", "aborted"}:
            cur.execute(
                """
                UPDATE executions
                SET status = %s, current_node_id = %s, final_context_json = %s, finished_at = now()
                WHERE id = %s
                """,
                (status, current_node_id, final_context_json, execution_id),
            )
        else:
            cur.execute(
                """
                UPDATE executions
                SET status = %s, current_node_id = %s
                WHERE id = %s
                """,
                (status, current_node_id, execution_id),
            )


def create_snapshot(
    conn: Connection,
    *,
    execution_id: UUID,
    event_index: int,
    context_json: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO execution_snapshots(execution_id, event_index, context_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (execution_id, event_index) DO NOTHING
            """,
            (execution_id, event_index, context_json),
        )


def list_events(conn: Connection, execution_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, execution_id, event_index, event_type, node_id, edge_id, payload, occurred_at
            FROM execution_events
            WHERE execution_id = %s
            ORDER BY event_index ASC
            """,
            (execution_id,),
        )
        return list(cur.fetchall())


def get_latest_snapshot_before(
    conn: Connection,
    execution_id: UUID,
    event_index: int,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, execution_id, event_index, context_json, created_at
            FROM execution_snapshots
            WHERE execution_id = %s AND event_index <= %s
            ORDER BY event_index DESC
            LIMIT 1
            """,
            (execution_id, event_index),
        )
        return cur.fetchone()
