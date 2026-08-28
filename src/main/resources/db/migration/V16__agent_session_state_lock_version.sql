-- Optimistic locking for agent_session_state.
-- AgentSessionService.upsert used an unchecked read-modify-write, so two concurrent
-- writers could silently drop each other's payload. lock_version backs a conditional
-- UPDATE ... WHERE lock_version = ? so conflicting writers must re-read and retry.
ALTER TABLE agent_session_state
  ADD COLUMN lock_version BIGINT NOT NULL DEFAULT 0;
