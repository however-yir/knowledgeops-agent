CREATE TABLE IF NOT EXISTS course (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  edu INT NULL,
  type VARCHAR(32) NULL,
  price BIGINT NULL,
  duration INT NULL
);

CREATE TABLE IF NOT EXISTS school (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  city VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS course_reservation (
  id INT PRIMARY KEY AUTO_INCREMENT,
  course VARCHAR(128) NOT NULL,
  student_name VARCHAR(64) NOT NULL,
  contact_info VARCHAR(128) NOT NULL,
  school VARCHAR(128) NOT NULL,
  remark VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS conversation (
  id BIGINT PRIMARY KEY,
  conversation_id VARCHAR(128) NOT NULL,
  message TEXT NOT NULL,
  type VARCHAR(32) NOT NULL,
  create_time DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversation_id_create_time
  ON conversation (conversation_id, create_time);

CREATE TABLE IF NOT EXISTS ingestion_job (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_id VARCHAR(64) NOT NULL UNIQUE,
  chat_id VARCHAR(128) NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  source_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(512) NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL UNIQUE,
  status VARCHAR(32) NOT NULL,
  trace_id VARCHAR(128) NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  error_message VARCHAR(1024) NULL,
  next_retry_at DATETIME NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingestion_status_next_retry
  ON ingestion_job (status, next_retry_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_chat_created
  ON ingestion_job (chat_id, created_at);

CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(128) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  role_name VARCHAR(64) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  permission_name VARCHAR(128) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_user_role (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  role_id BIGINT NOT NULL,
  permission_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_role_permission (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS api_keys (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  key_hash VARCHAR(128) NOT NULL UNIQUE,
  key_name VARCHAR(128) NOT NULL,
  role_name VARCHAR(64) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  last_used_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_id VARCHAR(128) NULL,
  trace_id VARCHAR(128) NULL,
  user_identity VARCHAR(255) NULL,
  method VARCHAR(16) NOT NULL,
  path VARCHAR(255) NOT NULL,
  status_code INT NOT NULL,
  duration_ms BIGINT NOT NULL,
  chat_id VARCHAR(128) NULL,
  job_id VARCHAR(128) NULL,
  extra_payload TEXT NULL,
  created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created
  ON audit_log (created_at);

INSERT IGNORE INTO roles (id, role_name, created_at) VALUES
  (1, 'ADMIN', NOW()),
  (2, 'USER', NOW()),
  (3, 'OPS', NOW());

INSERT IGNORE INTO permissions (id, permission_name, created_at) VALUES
  (1, 'chat:write', NOW()),
  (2, 'ingestion:write', NOW()),
  (3, 'metrics:read', NOW()),
  (4, 'audit:read', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at) VALUES
  (1, 1, NOW()),
  (1, 2, NOW()),
  (1, 3, NOW()),
  (1, 4, NOW()),
  (2, 1, NOW()),
  (2, 2, NOW()),
  (3, 3, NOW());

INSERT IGNORE INTO api_keys (key_hash, key_name, role_name, enabled, created_at, updated_at) VALUES
  ('6cbae51c7775b973f845b3fb4b333495890ecc9c57a9c3b3d662a3200d3227e1', 'dev-default-admin-key', 'ADMIN', 1, NOW(), NOW());
