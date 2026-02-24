from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb


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
            INSERT INTO api.workflows(name, description, created_by)
            VALUES (%s, %s, %s)
            RETURNING id, name, description, created_by, created_at
            """,
            (name, description, created_by),
        )
        return cur.fetchone()


def list_workflows(conn: Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              w.id,
              w.name,
              w.description,
              w.created_by,
              w.created_at,
              v.id AS latest_version_id,
              v.version_number AS latest_version_number,
              v.created_at AS latest_version_created_at,
              v.version_note AS latest_version_note,
              v.version_tag AS latest_version_tag
            FROM api.workflows w
            LEFT JOIN LATERAL (
              SELECT id, version_number, created_at, version_note, version_tag
              FROM api.workflow_versions
              WHERE workflow_id = w.id
              ORDER BY version_number DESC
              LIMIT 1
            ) v ON TRUE
            ORDER BY w.created_at DESC
            """
        )
        return list(cur.fetchall())


def create_workflow_version(
    conn: Connection,
    *,
    workflow_id: UUID,
    graph_json: dict[str, Any],
    version_note: str | None,
    version_tag: str | None,
    is_published: bool,
    created_by: str | None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM api.workflow_versions WHERE workflow_id = %s",
            (workflow_id,),
        )
        next_version = cur.fetchone()["next_version"]

        cur.execute(
            """
            INSERT INTO api.workflow_versions(
              workflow_id,
              version_number,
              graph_json,
              version_note,
              version_tag,
              is_published,
              created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, workflow_id, version_number, graph_json, version_note, version_tag, is_published, created_by, created_at
            """,
            (workflow_id, next_version, Jsonb(graph_json), version_note, version_tag, is_published, created_by),
        )
        row = cur.fetchone()

        return row


def list_workflow_versions(conn: Connection, workflow_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_id, version_number, version_note, version_tag, is_published, created_by, created_at
            FROM api.workflow_versions
            WHERE workflow_id = %s
            ORDER BY version_number DESC
            """,
            (workflow_id,),
        )
        return list(cur.fetchall())


def get_workflow(conn: Connection, workflow_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, created_by, created_at FROM api.workflows WHERE id = %s",
            (workflow_id,),
        )
        return cur.fetchone()


def get_workflow_version(conn: Connection, workflow_version_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_id, version_number, graph_json, version_note, version_tag, is_published, created_by, created_at
            FROM api.workflow_versions
            WHERE id = %s
            """,
            (workflow_version_id,),
        )
        return cur.fetchone()


def get_latest_workflow_version(conn: Connection, workflow_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_id, version_number, graph_json, version_note, version_tag, is_published, created_by, created_at
            FROM api.workflow_versions
            WHERE workflow_id = %s
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        return cur.fetchone()


def get_latest_published_workflow_version(conn: Connection, workflow_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_id, version_number, graph_json, version_note, version_tag, is_published, created_by, created_at
            FROM api.workflow_versions
            WHERE workflow_id = %s AND is_published = TRUE
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        return cur.fetchone()


def get_execution_by_idempotency_key(conn: Connection, idempotency_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_version_id, status, started_at, finished_at, debug_mode, current_node_id,
                   final_context_json,
                   parent_execution_id, trigger_type, trigger_payload, idempotency_key, correlation_id
            FROM api.executions
            WHERE idempotency_key = %s
            LIMIT 1
            """,
            (idempotency_key,),
        )
        return cur.fetchone()


def create_execution(
    conn: Connection,
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
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api.executions(
              workflow_version_id,
              status,
              started_at,
              debug_mode,
              current_node_id,
              input_json,
              parent_execution_id,
              trigger_type,
              trigger_payload,
              idempotency_key,
              correlation_id
            )
            VALUES (%s, 'running', now(), %s, NULL, %s, %s, %s, %s, %s, %s)
            RETURNING id, workflow_version_id, status, started_at, finished_at, debug_mode, current_node_id,
                      final_context_json,
                      parent_execution_id, trigger_type, trigger_payload, idempotency_key, correlation_id
            """,
            (
                workflow_version_id,
                debug_mode,
                Jsonb(input_json),
                parent_execution_id,
                trigger_type,
                Jsonb(trigger_payload),
                idempotency_key,
                correlation_id,
            ),
        )
        return cur.fetchone()


def get_execution(conn: Connection, execution_id: UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, workflow_version_id, status, started_at, finished_at, debug_mode, current_node_id,
                   final_context_json,
                   parent_execution_id, trigger_type, trigger_payload, idempotency_key, correlation_id
            FROM api.executions
            WHERE id = %s
            """,
            (execution_id,),
        )
        return cur.fetchone()


def get_next_event_index(conn: Connection, execution_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(event_index), -1) + 1 AS next_idx FROM api.execution_events WHERE execution_id = %s",
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
            INSERT INTO api.execution_events(execution_id, event_index, event_type, node_id, edge_id, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, execution_id, event_index, event_type, node_id, edge_id, payload, occurred_at
            """,
            (execution_id, event_index, event_type, node_id, edge_id, Jsonb(payload)),
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
                UPDATE api.executions
                SET status = %s, current_node_id = %s, final_context_json = %s, finished_at = now()
                WHERE id = %s
                """,
                (status, current_node_id, Jsonb(final_context_json) if final_context_json is not None else None, execution_id),
            )
        else:
            if final_context_json is None:
                cur.execute(
                    """
                    UPDATE api.executions
                    SET status = %s, current_node_id = %s
                    WHERE id = %s
                    """,
                    (status, current_node_id, execution_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE api.executions
                    SET status = %s, current_node_id = %s, final_context_json = %s
                    WHERE id = %s
                    """,
                    (status, current_node_id, Jsonb(final_context_json), execution_id),
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
            INSERT INTO api.execution_snapshots(execution_id, event_index, context_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (execution_id, event_index) DO NOTHING
            """,
            (execution_id, event_index, Jsonb(context_json)),
        )


def list_events(conn: Connection, execution_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, execution_id, event_index, event_type, node_id, edge_id, payload, occurred_at
            FROM api.execution_events
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
            FROM api.execution_snapshots
            WHERE execution_id = %s AND event_index <= %s
            ORDER BY event_index DESC
            LIMIT 1
            """,
            (execution_id, event_index),
        )
        return cur.fetchone()


def create_saved_output(
    conn: Connection,
    *,
    execution_id: UUID,
    key: str,
    value_json: dict[str, Any] | list[Any] | str | int | float | bool | None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api.saved_outputs(execution_id, key, value_json)
            VALUES (%s, %s, %s)
            RETURNING id, execution_id, key, value_json, created_at
            """,
            (execution_id, key, Jsonb(value_json)),
        )
        return cur.fetchone()
