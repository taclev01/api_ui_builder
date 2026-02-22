-- V1 Event-Sourced schema for API Logic Builder

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workflows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL,
  graph_json JSONB NOT NULL,
  is_published BOOLEAN NOT NULL DEFAULT FALSE,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(workflow_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_workflow_versions_workflow_id
  ON workflow_versions(workflow_id);

CREATE TABLE IF NOT EXISTS executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_version_id UUID NOT NULL REFERENCES workflow_versions(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('queued','running','paused','completed','failed','aborted')),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  debug_mode BOOLEAN NOT NULL DEFAULT FALSE,
  current_node_id TEXT,
  input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  final_context_json JSONB,
  parent_execution_id UUID REFERENCES executions(id) ON DELETE SET NULL,
  trigger_type TEXT,
  trigger_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT,
  correlation_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_executions_workflow_version_id
  ON executions(workflow_version_id);
CREATE INDEX IF NOT EXISTS idx_executions_status
  ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_parent_execution_id
  ON executions(parent_execution_id);
CREATE INDEX IF NOT EXISTS idx_executions_correlation_id
  ON executions(correlation_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_idempotency_key_unique
  ON executions(idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS execution_events (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
  event_index BIGINT NOT NULL,
  event_type TEXT NOT NULL,
  node_id TEXT,
  edge_id TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(execution_id, event_index)
);

CREATE INDEX IF NOT EXISTS idx_execution_events_execution_id
  ON execution_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_event_type
  ON execution_events(event_type);

CREATE TABLE IF NOT EXISTS execution_snapshots (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
  event_index BIGINT NOT NULL,
  context_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(execution_id, event_index)
);

CREATE INDEX IF NOT EXISTS idx_execution_snapshots_execution_id
  ON execution_snapshots(execution_id);

CREATE TABLE IF NOT EXISTS saved_outputs (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_outputs_execution_id
  ON saved_outputs(execution_id);
