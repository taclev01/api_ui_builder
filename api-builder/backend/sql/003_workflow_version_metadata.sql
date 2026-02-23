-- Add optional user-facing metadata for version naming/history.

ALTER TABLE api.workflow_versions
  ADD COLUMN IF NOT EXISTS version_note TEXT;

ALTER TABLE api.workflow_versions
  ADD COLUMN IF NOT EXISTS version_tag TEXT;
