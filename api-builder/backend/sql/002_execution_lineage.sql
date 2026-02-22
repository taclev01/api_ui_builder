-- Add execution lineage + trigger metadata for workflow-to-workflow invocation.

ALTER TABLE executions
  ADD COLUMN IF NOT EXISTS parent_execution_id UUID REFERENCES executions(id) ON DELETE SET NULL;

ALTER TABLE executions
  ADD COLUMN IF NOT EXISTS trigger_type TEXT;

ALTER TABLE executions
  ADD COLUMN IF NOT EXISTS trigger_payload JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE executions
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

ALTER TABLE executions
  ADD COLUMN IF NOT EXISTS correlation_id TEXT;

CREATE INDEX IF NOT EXISTS idx_executions_parent_execution_id
  ON executions(parent_execution_id);

CREATE INDEX IF NOT EXISTS idx_executions_correlation_id
  ON executions(correlation_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_idempotency_key_unique
  ON executions(idempotency_key)
  WHERE idempotency_key IS NOT NULL;
