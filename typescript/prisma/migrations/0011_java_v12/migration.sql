CREATE TABLE IF NOT EXISTS memory_item (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  memory_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  user_id VARCHAR(64) NULL,
  type VARCHAR(32) NOT NULL DEFAULT 'short',
  content TEXT NOT NULL,
  source VARCHAR(128) NULL,
  source_task_id VARCHAR(64) NULL,
  confidence DOUBLE NOT NULL DEFAULT 0.8,
  metadata_json JSON NULL,
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_memory_item_id (memory_id),
  INDEX idx_memory_item_tenant_user_type (tenant_id, user_id, type),
  INDEX idx_memory_item_tenant_type (tenant_id, type),
  INDEX idx_memory_item_expires (expires_at),
  INDEX idx_memory_item_source_task (source_task_id)
);

CREATE TABLE IF NOT EXISTS memory_event (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  memory_id VARCHAR(64) NOT NULL,
  action VARCHAR(32) NOT NULL,
  reason VARCHAR(512) NULL,
  metadata_json JSON NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_memory_event_id (event_id),
  INDEX idx_memory_event_memory (memory_id),
  INDEX idx_memory_event_created (created_at)
);
