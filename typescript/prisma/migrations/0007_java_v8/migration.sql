CREATE TABLE IF NOT EXISTS agent_session_state (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(128) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  title VARCHAR(255) NOT NULL,
  workspace_id VARCHAR(64) NOT NULL DEFAULT 'default',
  model_profile VARCHAR(32) NOT NULL DEFAULT 'balanced',
  streaming TINYINT(1) NOT NULL DEFAULT 1,
  pinned TINYINT(1) NOT NULL DEFAULT 0,
  archived TINYINT(1) NOT NULL DEFAULT 0,
  active_branch_id VARCHAR(128) NULL,
  session_payload LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_agent_session_tenant_session (tenant_id, session_id)
);

CREATE INDEX idx_agent_session_tenant_updated
  ON agent_session_state (tenant_id, updated_at);

CREATE INDEX idx_agent_session_tenant_pin_archive_updated
  ON agent_session_state (tenant_id, pinned, archived, updated_at);

CREATE TABLE IF NOT EXISTS answer_feedback (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  chat_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128) NULL,
  branch_id VARCHAR(128) NULL,
  message_id VARCHAR(128) NULL,
  rating INT NOT NULL,
  comment VARCHAR(1024) NULL,
  question_text TEXT NULL,
  answer_text TEXT NULL,
  created_at DATETIME NOT NULL
);

CREATE INDEX idx_answer_feedback_tenant_created
  ON answer_feedback (tenant_id, created_at);

CREATE TABLE IF NOT EXISTS tenant_budget (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  monthly_budget_usd DECIMAL(12, 4) NOT NULL DEFAULT 25.0000,
  hard_limit_enabled TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_tenant_budget_tenant (tenant_id)
);

CREATE TABLE IF NOT EXISTS tenant_usage_daily (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  usage_date DATE NOT NULL,
  request_count BIGINT NOT NULL DEFAULT 0,
  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  total_cost_usd DECIMAL(14, 6) NOT NULL DEFAULT 0.000000,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_tenant_usage_daily_tenant_date (tenant_id, usage_date)
);

CREATE INDEX idx_tenant_usage_daily_tenant_date
  ON tenant_usage_daily (tenant_id, usage_date);

CREATE TABLE IF NOT EXISTS model_ab_exposure (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  experiment_key VARCHAR(64) NOT NULL,
  subject_key VARCHAR(128) NOT NULL,
  endpoint VARCHAR(32) NOT NULL,
  bucket INT NOT NULL,
  variant VARCHAR(32) NOT NULL,
  routed_profile VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE INDEX idx_model_ab_exposure_tenant_created
  ON model_ab_exposure (tenant_id, created_at);

INSERT IGNORE INTO tenant_budget (
  tenant_id,
  monthly_budget_usd,
  hard_limit_enabled,
  created_at,
  updated_at
) VALUES (
  'public',
  25.0000,
  0,
  NOW(),
  NOW()
);

INSERT IGNORE INTO permissions (permission_name, created_at) VALUES
  ('session:read', NOW()),
  ('session:write', NOW()),
  ('feedback:write', NOW()),
  ('cost:read', NOW()),
  ('cost:write', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at)
SELECT r.id, p.id, NOW()
FROM roles r
INNER JOIN permissions p ON (
  (r.role_name = 'ADMIN' AND p.permission_name IN (
    'session:read', 'session:write', 'feedback:write', 'cost:read', 'cost:write'
  ))
  OR (r.role_name = 'USER' AND p.permission_name IN (
    'session:read', 'session:write', 'feedback:write', 'cost:read'
  ))
  OR (r.role_name = 'OPS' AND p.permission_name IN (
    'session:read', 'cost:read'
  ))
);
