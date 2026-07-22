ALTER TABLE conversation
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

DROP INDEX idx_conversation_id_create_time ON conversation;

CREATE INDEX idx_conversation_tenant_conversation_create
  ON conversation (tenant_id, conversation_id, create_time);

ALTER TABLE ingestion_job
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

ALTER TABLE ingestion_job
  DROP INDEX idempotency_key;

ALTER TABLE ingestion_job
  ADD UNIQUE KEY uk_ingestion_tenant_idempotency (tenant_id, idempotency_key);

CREATE INDEX idx_ingestion_tenant_chat_created
  ON ingestion_job (tenant_id, chat_id, created_at);

CREATE INDEX idx_ingestion_tenant_status_next_retry
  ON ingestion_job (tenant_id, status, next_retry_at);
