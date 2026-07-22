ALTER TABLE ingestion_job
  ADD COLUMN content_hash VARCHAR(64) NULL,
  ADD COLUMN raw_text LONGTEXT NULL,
  ADD COLUMN lease_owner VARCHAR(128) NULL,
  ADD COLUMN lease_expires_at DATETIME NULL,
  ADD COLUMN version INT NOT NULL DEFAULT 0;

CREATE INDEX idx_ingestion_status_lease
  ON ingestion_job (status, lease_expires_at);

CREATE TABLE IF NOT EXISTS knowledge_chunk (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  chunk_id VARCHAR(128) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  chat_id VARCHAR(128) NOT NULL,
  job_id VARCHAR(64) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  chunk_index INT NOT NULL,
  content LONGTEXT NOT NULL,
  metadata_json JSON NULL,
  vector_json JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_knowledge_chunk_id (chunk_id),
  UNIQUE KEY uk_knowledge_chunk_tenant_job_index (tenant_id, job_id, chunk_index)
);

CREATE INDEX idx_knowledge_chunk_tenant_chat
  ON knowledge_chunk (tenant_id, chat_id, chunk_index);
CREATE INDEX idx_knowledge_chunk_tenant_source
  ON knowledge_chunk (tenant_id, source_type);

CREATE TABLE IF NOT EXISTS harness_event (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  action VARCHAR(64) NOT NULL,
  source VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  latency_ms BIGINT NOT NULL DEFAULT 0,
  payload_json JSON NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_harness_event_id (event_id)
);

CREATE INDEX idx_harness_event_action_status
  ON harness_event (action, status);
CREATE INDEX idx_harness_event_tenant_created
  ON harness_event (tenant_id, created_at);
CREATE INDEX idx_harness_event_created
  ON harness_event (created_at);
