CREATE TABLE IF NOT EXISTS agent_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  type VARCHAR(32) NOT NULL DEFAULT 'REACT',
  status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
  user_input TEXT NOT NULL,
  final_output LONGTEXT NULL,
  model_profile VARCHAR(32) NOT NULL DEFAULT 'balanced',
  chat_id VARCHAR(128) NULL,
  session_id VARCHAR(128) NULL,
  metadata_json JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_agent_task_id (task_id),
  INDEX idx_agent_task_tenant_status (tenant_id, status),
  INDEX idx_agent_task_tenant_created (tenant_id, created_at),
  INDEX idx_agent_task_session (session_id)
);

CREATE TABLE IF NOT EXISTS agent_step (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  step_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  agent_name VARCHAR(64) NOT NULL DEFAULT 'planner',
  status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
  step_order INT NOT NULL DEFAULT 0,
  input_json JSON NULL,
  output_json JSON NULL,
  thought TEXT NULL,
  action VARCHAR(64) NULL,
  action_input_json JSON NULL,
  observation_json JSON NULL,
  model_profile VARCHAR(32) NULL,
  input_tokens BIGINT NULL DEFAULT 0,
  output_tokens BIGINT NULL DEFAULT 0,
  latency_ms BIGINT NULL DEFAULT 0,
  error_message TEXT NULL,
  started_at DATETIME NOT NULL,
  ended_at DATETIME NULL,
  UNIQUE KEY uk_agent_step_id (step_id),
  INDEX idx_agent_step_task (task_id),
  INDEX idx_agent_step_task_order (task_id, step_order)
);

CREATE TABLE IF NOT EXISTS agent_event (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  step_id VARCHAR(64) NULL,
  event_type VARCHAR(32) NOT NULL,
  payload_json JSON NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_agent_event_id (event_id),
  INDEX idx_agent_event_task (task_id),
  INDEX idx_agent_event_task_type (task_id, event_type),
  INDEX idx_agent_event_created (created_at)
);
