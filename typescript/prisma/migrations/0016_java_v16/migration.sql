-- Optimistic locking for agent_session_state (mirror of the Java V16 migration).
-- Concurrent writers of the same session row must re-read on lock_version
-- conflicts instead of silently dropping each other's payload.
ALTER TABLE agent_session_state
  ADD COLUMN lock_version BIGINT NOT NULL DEFAULT 0;
