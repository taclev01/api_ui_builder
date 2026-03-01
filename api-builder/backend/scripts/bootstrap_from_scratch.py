#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/api_builder"
DEFAULT_WORKFLOW_NAME = "first workflow"
DEFAULT_WORKFLOW_DESCRIPTION = "Seeded example workflow for API Flow Builder POC."
DEFAULT_VERSION_TAG = "seed-example"
DEFAULT_VERSION_NOTE = "Seeded runnable example using mock_api endpoints."
DEFAULT_MOCK_API_BASE_URL = "http://localhost:8010"
DEFAULT_CREATED_BY = "bootstrap-script"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def build_example_graph(mock_api_base_url: str) -> dict[str, Any]:
    base_url = mock_api_base_url.rstrip("/")
    return {
        "entry_node_id": "n-1",
        "nodes": [
            {
                "id": "n-1",
                "type": "start_request",
                "position": {"x": 120, "y": 120},
                "data": {
                    "label": "Start (Request)",
                    "nodeType": "start_request",
                    "config": {
                        "method": "GET",
                        "url": "{{vars.mock_api_base_url}}/auth/check",
                        "authRef": "n-13::demo_bearer",
                        "timeoutMs": 10000,
                        "retryAttempts": 2,
                        "backoff": "exponential",
                    },
                },
            },
            {
                "id": "n-2",
                "type": "form_request",
                "position": {"x": 120, "y": 280},
                "data": {
                    "label": "Get users",
                    "nodeType": "form_request",
                    "config": {
                        "method": "GET",
                        "url": "{{vars.mock_api_base_url}}/users?page=1&page_size={{vars.page_size}}&active_only=true",
                        "timeoutMs": 10000,
                        "retryAttempts": 2,
                        "backoff": "exponential",
                        "circuitFailureThreshold": 5,
                        "circuitOpenMs": 30000,
                    },
                },
            },
            {
                "id": "n-3",
                "type": "define_variable",
                "position": {"x": 120, "y": 440},
                "data": {
                    "label": "Define user_count",
                    "nodeType": "define_variable",
                    "config": {
                        "name": "user_count",
                        "source": "last_response",
                        "selector": "body.total",
                        "defaultValue": 0,
                    },
                },
            },
            {
                "id": "n-4",
                "type": "if",
                "position": {"x": 120, "y": 600},
                "data": {
                    "label": "If enough users",
                    "nodeType": "if",
                    "config": {
                        "expression": "vars.user_count > vars.min_user_count",
                    },
                },
            },
            {
                "id": "n-5",
                "type": "paginate_request",
                "position": {"x": -40, "y": 760},
                "data": {
                    "label": "Load orders pages",
                    "nodeType": "paginate_request",
                    "config": {
                        "method": "GET",
                        "url": "{{vars.mock_api_base_url}}/orders",
                        "authRef": "",
                        "strategy": "page_number",
                        "itemsPath": "body.data",
                        "nextCursorPath": "body.next_page",
                        "hasMorePath": "body.next_page",
                        "maxPages": 3,
                        "pageSize": 20,
                        "timeoutMs": 10000,
                        "retryAttempts": 2,
                        "backoff": "exponential",
                    },
                },
            },
            {
                "id": "n-6",
                "type": "form_request",
                "position": {"x": -40, "y": 920},
                "data": {
                    "label": "Load fanout targets",
                    "nodeType": "form_request",
                    "config": {
                        "method": "GET",
                        "url": "{{vars.mock_api_base_url}}/fanout/targets?count={{vars.target_count}}",
                        "timeoutMs": 10000,
                        "retryAttempts": 2,
                        "backoff": "exponential",
                        "circuitFailureThreshold": 5,
                        "circuitOpenMs": 30000,
                    },
                },
            },
            {
                "id": "n-7",
                "type": "for_each_parallel",
                "position": {"x": -40, "y": 1080},
                "data": {
                    "label": "For each target",
                    "nodeType": "for_each_parallel",
                    "config": {
                        "listExpr": "last_response.body.targets",
                        "itemName": "target",
                        "maxConcurrency": 5,
                    },
                },
            },
            {
                "id": "n-8",
                "type": "join",
                "position": {"x": -40, "y": 1240},
                "data": {
                    "label": "Gather parallel context",
                    "nodeType": "join",
                    "config": {"mergeStrategy": "collect_list"},
                },
            },
            {
                "id": "n-9",
                "type": "python_request",
                "position": {"x": -40, "y": 1400},
                "data": {
                    "label": "Build summary (Python)",
                    "nodeType": "python_request",
                    "config": {
                        "functionName": "build_summary",
                        "authRef": "",
                        "timeoutMs": 10000,
                        "retryAttempts": 0,
                        "backoff": "fixed",
                        "code": (
                            "def build_summary(context):\n"
                            "    vars_data = context.get('vars', {})\n"
                            "    user_count = int(vars_data.get('user_count', 0))\n"
                            "    targets = vars_data.get('target_items', [])\n"
                            "    return {\n"
                            "        'status_code': 200,\n"
                            "        'body': {\n"
                            "            'summary': {\n"
                            "                'user_count': user_count,\n"
                            "                'targets_count': len(targets),\n"
                            "                'targets_preview': targets[:3],\n"
                            "                'source': 'python_request'\n"
                            "            }\n"
                            "        }\n"
                            "    }\n"
                        ),
                    },
                },
            },
            {
                "id": "n-10",
                "type": "save",
                "position": {"x": -40, "y": 1560},
                "data": {
                    "label": "Save summary",
                    "nodeType": "save",
                    "config": {
                        "key": "example_summary",
                        "from": "last_response.body.summary",
                    },
                },
            },
            {
                "id": "n-11",
                "type": "end",
                "position": {"x": -40, "y": 1720},
                "data": {
                    "label": "End",
                    "nodeType": "end",
                    "config": {},
                },
            },
            {
                "id": "n-12",
                "type": "raise_error",
                "position": {"x": 280, "y": 760},
                "data": {
                    "label": "Not enough users",
                    "nodeType": "raise_error",
                    "config": {
                        "message": "Not enough users: {{vars.user_count}} <= {{vars.min_user_count}}",
                    },
                },
            },
            {
                "id": "n-13",
                "type": "auth",
                "position": {"x": 520, "y": 120},
                "data": {
                    "label": "Auth",
                    "nodeType": "auth",
                    "config": {
                        "authList": [
                            {
                                "name": "demo_bearer",
                                "authType": "bearer",
                                "tokenVar": "vars.token",
                                "headerName": "Authorization",
                            }
                        ],
                        "authType": "bearer",
                        "tokenVar": "vars.token",
                        "headerName": "Authorization",
                    },
                },
            },
            {
                "id": "n-14",
                "type": "parameters",
                "position": {"x": 520, "y": 280},
                "data": {
                    "label": "Parameters",
                    "nodeType": "parameters",
                    "config": {
                        "parameters": [
                            {
                                "name": "mock_api_base_url",
                                "type": "string",
                                "defaultValue": base_url,
                                "description": "Base URL for local mock API service",
                            },
                            {
                                "name": "token",
                                "type": "string",
                                "defaultValue": "demo-token",
                                "description": "Bearer token used by Auth node",
                            },
                            {
                                "name": "page_size",
                                "type": "number",
                                "defaultValue": 20,
                                "description": "Users page size",
                            },
                            {
                                "name": "min_user_count",
                                "type": "number",
                                "defaultValue": 20,
                                "description": "If threshold for user_count",
                            },
                            {
                                "name": "target_count",
                                "type": "number",
                                "defaultValue": 5,
                                "description": "Fanout target count",
                            },
                        ]
                    },
                },
            },
        ],
        "edges": [
            {
                "id": "e-1-2",
                "source": "n-1",
                "target": "n-2",
                "type": "breakpoint",
                "data": {"breakpoint": True},
            },
            {
                "id": "e-2-3",
                "source": "n-2",
                "target": "n-3",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-3-4",
                "source": "n-3",
                "target": "n-4",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-4-5",
                "source": "n-4",
                "sourceHandle": "true",
                "target": "n-5",
                "type": "breakpoint",
                "label": "TRUE",
                "data": {"breakpoint": False, "condition": "true"},
            },
            {
                "id": "e-4-12",
                "source": "n-4",
                "sourceHandle": "false",
                "target": "n-12",
                "type": "breakpoint",
                "label": "FALSE",
                "data": {"breakpoint": True, "condition": "false"},
            },
            {
                "id": "e-5-6",
                "source": "n-5",
                "target": "n-6",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-6-7",
                "source": "n-6",
                "target": "n-7",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-7-8",
                "source": "n-7",
                "target": "n-8",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-8-9",
                "source": "n-8",
                "target": "n-9",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-9-10",
                "source": "n-9",
                "target": "n-10",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
            {
                "id": "e-10-11",
                "source": "n-10",
                "target": "n-11",
                "type": "breakpoint",
                "data": {"breakpoint": False},
            },
        ],
    }


def ensure_database_exists(database_url: str) -> None:
    info = conninfo_to_dict(database_url)
    dbname = info.get("dbname")
    if not dbname:
        raise RuntimeError("Could not resolve target dbname from DATABASE_URL")

    admin_info = dict(info)
    admin_info["dbname"] = "postgres"
    admin_dsn = make_conninfo(**admin_info)

    try:
        with psycopg.connect(admin_dsn, row_factory=dict_row, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
                    print(f"[db] created database '{dbname}'")
                else:
                    print(f"[db] database '{dbname}' already exists")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed ensuring database '{dbname}'. "
            "Verify your DATABASE_URL credentials and privileges."
        ) from exc


def apply_migrations(conn: psycopg.Connection[Any], sql_dir: Path) -> list[str]:
    pattern = re.compile(r"^\d+_.+\.sql$")
    migration_files = sorted(path for path in sql_dir.glob("*.sql") if pattern.match(path.name))
    if not migration_files:
        raise RuntimeError(f"No migration files found in {sql_dir}")

    applied: list[str] = []
    for path in migration_files:
        sql_text = path.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql_text)
        applied.append(path.name)
        print(f"[migrate] applied {path.name}")
    conn.commit()
    return applied


def seed_example_workflow(
    conn: psycopg.Connection[Any],
    *,
    workflow_name: str,
    workflow_description: str,
    version_tag: str,
    version_note: str,
    created_by: str,
    mock_api_base_url: str,
    force_new_version: bool,
) -> dict[str, Any]:
    graph = build_example_graph(mock_api_base_url)
    graph_sig = canonical_json(graph)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name
            FROM api.workflows
            WHERE name = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workflow_name,),
        )
        workflow = cur.fetchone()

        if workflow is None:
            cur.execute(
                """
                INSERT INTO api.workflows(name, description, created_by)
                VALUES (%s, %s, %s)
                RETURNING id, name
                """,
                (workflow_name, workflow_description, created_by),
            )
            workflow = cur.fetchone()
            print(f"[seed] created workflow '{workflow_name}'")
        else:
            print(f"[seed] using existing workflow '{workflow_name}'")

        workflow_id = workflow["id"]

        cur.execute(
            """
            SELECT id, version_number, graph_json
            FROM api.workflow_versions
            WHERE workflow_id = %s
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        latest = cur.fetchone()

        if latest is not None and not force_new_version:
            latest_sig = canonical_json(latest["graph_json"])
            if latest_sig == graph_sig:
                conn.commit()
                print(f"[seed] latest version already matches seed graph (v{latest['version_number']})")
                return {
                    "workflow_id": str(workflow_id),
                    "workflow_name": workflow_name,
                    "workflow_version_id": str(latest["id"]),
                    "version_number": int(latest["version_number"]),
                    "created_new_version": False,
                }

        next_version = 1 if latest is None else int(latest["version_number"]) + 1
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
            VALUES (%s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id, version_number
            """,
            (
                workflow_id,
                next_version,
                Jsonb(graph),
                version_note,
                version_tag,
                created_by,
            ),
        )
        version = cur.fetchone()
        conn.commit()
        print(f"[seed] created workflow version v{version['version_number']}")
        return {
            "workflow_id": str(workflow_id),
            "workflow_name": workflow_name,
            "workflow_version_id": str(version["id"]),
            "version_number": int(version["version_number"]),
            "created_new_version": True,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local DB and seed example workflow.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Postgres connection string for target application DB.",
    )
    parser.add_argument(
        "--mock-api-base-url",
        default=os.environ.get("MOCK_API_BASE_URL", DEFAULT_MOCK_API_BASE_URL),
        help="Base URL used in seeded request nodes.",
    )
    parser.add_argument(
        "--workflow-name",
        default=DEFAULT_WORKFLOW_NAME,
        help="Workflow name for the seeded example flow.",
    )
    parser.add_argument(
        "--workflow-description",
        default=DEFAULT_WORKFLOW_DESCRIPTION,
        help="Description for the seeded workflow.",
    )
    parser.add_argument(
        "--version-tag",
        default=DEFAULT_VERSION_TAG,
        help="Version tag for the seeded graph.",
    )
    parser.add_argument(
        "--version-note",
        default=DEFAULT_VERSION_NOTE,
        help="Version note for the seeded graph.",
    )
    parser.add_argument(
        "--created-by",
        default=DEFAULT_CREATED_BY,
        help="Value stored in created_by fields.",
    )
    parser.add_argument(
        "--force-new-version",
        action="store_true",
        help="Always create a new version even if the latest version graph is identical.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sql_dir = Path(__file__).resolve().parents[1] / "sql"

    print(f"[setup] DATABASE_URL={args.database_url}")
    ensure_database_exists(args.database_url)

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        applied = apply_migrations(conn, sql_dir)
        seed_summary = seed_example_workflow(
            conn,
            workflow_name=args.workflow_name,
            workflow_description=args.workflow_description,
            version_tag=args.version_tag,
            version_note=args.version_note,
            created_by=args.created_by,
            mock_api_base_url=args.mock_api_base_url,
            force_new_version=args.force_new_version,
        )

    output = {
        "migrations_applied": applied,
        "seed": seed_summary,
        "next_steps": {
            "backend": "uv run uvicorn backend.app.main:app --reload --port 8000",
            "frontend": "npm run dev",
            "mock_api": "uv run uvicorn mock_api.app.main:app --reload --port 8010",
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
