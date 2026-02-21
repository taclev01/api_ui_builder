# API Logic Builder V1 Spec (Event-Sourced)

## Goals

- Provide a ReactFlow-based editor for composing API logic as a directed graph.
- Execute graphs synchronously in a Python backend.
- Support replay/time-travel debugging from immutable execution events.
- Keep v1 single-instance friendly while remaining Kubernetes-ready.

## Runtime Model

A workflow definition is immutable once published as a `workflow_version`.

Execution is event-sourced:

- The runtime evaluates one node transition at a time.
- Every significant action writes an `execution_event` row.
- Current state is derived from an in-memory `ExecutionContext` plus event history.
- Periodic snapshots (`execution_snapshots`) allow fast state reconstruction for time-travel.

## Graph Schema (stored as JSONB)

```json
{
  "nodes": [
    {
      "id": "node_1",
      "type": "start|end|if|define_variable|for_each_parallel|join|form_request|python_request|auth|save|delay|raise_error",
      "label": "Human readable",
      "config": {}
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "node_1",
      "target": "node_2",
      "condition": null,
      "breakpoint": false,
      "label": "optional"
    }
  ],
  "entry_node_id": "node_1"
}
```

## Required Node Types (v1)

- `start`: execution entry point.
- `end`: terminal success.
- `if`: evaluates an expression against context and routes via conditional edges.
- `define_variable`: extracts/transforms values from node outputs/context.
- `for_each_parallel`: fans out over list values (v1 may execute sequentially behind API, but event model supports future parallelism).
- `join`: merges branch outputs using declared merge strategy.
- `form_request`: declarative HTTP request node.
- `python_request`: user-defined Python function node.
- `auth`: reusable auth material/configuration (non-flow-linked metadata node is allowed).
- `save`: persists selected values for result reporting.
- `delay`: optional pause/rate control.
- `raise_error`: explicit failure/abort node.

## Context Contract

```json
{
  "vars": {},
  "nodes": {
    "<node_id>": {
      "output": {},
      "status": "success|failed|skipped"
    }
  },
  "system": {
    "run_id": "uuid",
    "started_at": "iso8601",
    "retry_state": {}
  }
}
```

Rules:

- Node output is written to `context.nodes[node_id].output`.
- Shared mutable values live in `context.vars`.
- Merge behavior at `join` is explicit in node config.

## Event Types

- `RUN_STARTED`
- `NODE_STARTED`
- `NODE_SUCCEEDED`
- `NODE_FAILED`
- `EDGE_TRAVERSED`
- `BREAKPOINT_PAUSED`
- `RUN_RESUMED`
- `RUN_ABORTED`
- `RUN_COMPLETED`
- `SNAPSHOT_WRITTEN`

`execution_events.payload` stores structured details (`node_id`, `edge_id`, `error`, `delta`, debug metadata).

## Debugging & Breakpoints

Edge config supports:

```json
{
  "breakpoint": true
}
```

On breakpoint edge traversal intent:

1. Write `BREAKPOINT_PAUSED` event with full cursor metadata.
2. Transition execution status to `paused`.
3. Wait for debug command via REST (`resume`, `step`, `abort`).

Replay includes pause/resume events, preserving exact debugging timeline.

## Reliability Policies

For `form_request` and `python_request`:

```json
{
  "timeout_ms": 10000,
  "retry": {
    "max_attempts": 3,
    "backoff": "exponential",
    "base_delay_ms": 200
  },
  "circuit_breaker": {
    "failure_threshold": 5,
    "open_ms": 30000
  }
}
```

## REST API (v1)

- `POST /workflows`
- `GET /workflows/{workflow_id}`
- `POST /workflows/{workflow_id}/versions`
- `POST /executions`
- `GET /executions/{run_id}`
- `GET /executions/{run_id}/events`
- `GET /executions/{run_id}/state?event_index=123`
- `POST /executions/{run_id}/debug/resume`
- `POST /executions/{run_id}/debug/step`
- `POST /executions/{run_id}/debug/abort`

## Storage Design (Postgres)

Use Postgres + JSONB with append-only execution events.

Core tables:

- `workflows`
- `workflow_versions`
- `executions`
- `execution_events`
- `execution_snapshots`
- `saved_outputs` (materialized result artifacts)

Design choices:

- Immutable `workflow_versions` for deterministic replay.
- Append-only `execution_events` for auditability and time-travel.
- Snapshot checkpoints to avoid replaying full histories for every query.

## Deployment Path

- v1 POC: single FastAPI instance + Postgres.
- Scale-up path:
  - split executor into worker deployment,
  - use queue for run dispatch,
  - retain shared Postgres event store,
  - add horizontal pods in Kubernetes.
