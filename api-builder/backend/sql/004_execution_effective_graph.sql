-- Persist the exact graph snapshot used to start an execution so debug resume/step
-- always evaluates against the same graph, even with unsaved frontend edits.
ALTER TABLE api.executions
  ADD COLUMN IF NOT EXISTS effective_graph_json JSONB;
