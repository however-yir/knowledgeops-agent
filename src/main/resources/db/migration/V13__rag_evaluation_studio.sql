CREATE TABLE IF NOT EXISTS eval_dataset (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  dataset_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  name VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  baseline_run_id VARCHAR(64) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_eval_dataset_tenant_dataset (tenant_id, dataset_id),
  INDEX idx_eval_dataset_tenant_updated (tenant_id, updated_at)
);

CREATE TABLE IF NOT EXISTS eval_case (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  case_id VARCHAR(64) NOT NULL,
  dataset_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  category VARCHAR(64) NULL,
  chat_id VARCHAR(128) NULL,
  question_text TEXT NOT NULL,
  expected_citations_json TEXT NULL,
  expected_keywords_json TEXT NULL,
  forbidden_keywords_json TEXT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_eval_case_tenant_dataset_case (tenant_id, dataset_id, case_id),
  INDEX idx_eval_case_tenant_dataset (tenant_id, dataset_id, sort_order)
);

CREATE TABLE IF NOT EXISTS eval_run (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  dataset_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  status VARCHAR(32) NOT NULL,
  model_profile VARCHAR(32) NOT NULL DEFAULT 'balanced',
  total_cases INT NOT NULL DEFAULT 0,
  passed_cases INT NOT NULL DEFAULT 0,
  run_score DOUBLE NOT NULL DEFAULT 0,
  retrieval_hit_rate DOUBLE NOT NULL DEFAULT 0,
  citation_coverage_rate DOUBLE NOT NULL DEFAULT 0,
  answer_faithfulness_score DOUBLE NOT NULL DEFAULT 0,
  avg_latency_ms DOUBLE NOT NULL DEFAULT 0,
  failure_rate DOUBLE NOT NULL DEFAULT 0,
  error_message VARCHAR(1024) NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_eval_run_tenant_run (tenant_id, run_id),
  INDEX idx_eval_run_tenant_dataset_created (tenant_id, dataset_id, created_at)
);

CREATE TABLE IF NOT EXISTS eval_result (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  result_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  dataset_id VARCHAR(64) NOT NULL,
  case_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  status VARCHAR(32) NOT NULL,
  question_text TEXT NOT NULL,
  answer_text LONGTEXT NULL,
  citations_json TEXT NULL,
  evidence_json TEXT NULL,
  retrieval_hit DOUBLE NOT NULL DEFAULT 0,
  citation_coverage DOUBLE NOT NULL DEFAULT 0,
  keyword_score DOUBLE NOT NULL DEFAULT 0,
  answer_faithfulness DOUBLE NOT NULL DEFAULT 0,
  score DOUBLE NOT NULL DEFAULT 0,
  latency_ms BIGINT NOT NULL DEFAULT 0,
  error_message VARCHAR(1024) NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_eval_result_tenant_result (tenant_id, result_id),
  INDEX idx_eval_result_tenant_run (tenant_id, run_id, id),
  INDEX idx_eval_result_tenant_dataset_case (tenant_id, dataset_id, case_id)
);

INSERT IGNORE INTO permissions (permission_name, created_at) VALUES
  ('eval:read', NOW()),
  ('eval:write', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at)
SELECT r.id, p.id, NOW()
FROM roles r
INNER JOIN permissions p ON (
  (r.role_name = 'ADMIN' AND p.permission_name IN ('eval:read', 'eval:write'))
  OR (r.role_name = 'USER' AND p.permission_name IN ('eval:read', 'eval:write'))
  OR (r.role_name = 'OPS' AND p.permission_name IN ('eval:read'))
);
