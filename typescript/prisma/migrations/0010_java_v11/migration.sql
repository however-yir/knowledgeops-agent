CREATE TABLE IF NOT EXISTS kg_entity (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  entity_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  name VARCHAR(255) NOT NULL,
  type VARCHAR(64) NOT NULL DEFAULT 'CONCEPT',
  aliases JSON NULL,
  description TEXT NULL,
  source_id VARCHAR(128) NULL,
  metadata_json JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_kg_entity_id (entity_id),
  INDEX idx_kg_entity_tenant_type (tenant_id, type),
  INDEX idx_kg_entity_tenant_name (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS kg_relation (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  relation_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  source_entity_id VARCHAR(64) NOT NULL,
  target_entity_id VARCHAR(64) NOT NULL,
  relation_type VARCHAR(64) NOT NULL DEFAULT 'RELATED_TO',
  evidence_id VARCHAR(128) NULL,
  weight DOUBLE NOT NULL DEFAULT 1.0,
  metadata_json JSON NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_kg_relation_id (relation_id),
  INDEX idx_kg_relation_tenant_source (tenant_id, source_entity_id),
  INDEX idx_kg_relation_tenant_target (tenant_id, target_entity_id),
  INDEX idx_kg_relation_tenant_type (tenant_id, relation_type)
);

CREATE TABLE IF NOT EXISTS kg_fact (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  fact_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'public',
  subject VARCHAR(255) NOT NULL,
  predicate VARCHAR(255) NOT NULL,
  object VARCHAR(512) NOT NULL,
  valid_from DATE NULL,
  valid_to DATE NULL,
  confidence DOUBLE NOT NULL DEFAULT 0.8,
  source VARCHAR(255) NULL,
  metadata_json JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_kg_fact_id (fact_id),
  INDEX idx_kg_fact_tenant_subject (tenant_id, subject),
  INDEX idx_kg_fact_tenant_predicate (tenant_id, predicate),
  INDEX idx_kg_fact_tenant_confidence (tenant_id, confidence)
);

-- Seed demo course graph entities
INSERT IGNORE INTO kg_entity (entity_id, tenant_id, name, type, aliases, description, created_at, updated_at) VALUES
('ent-course-java', 'public', 'Java编程实战', 'COURSE', '["Java","Java课程","Java实战"]', '面向初学者的Java编程课程', NOW(), NOW()),
('ent-course-python', 'public', 'Python数据分析', 'COURSE', '["Python","Python课程","数据分析"]', 'Python数据分析与机器学习入门', NOW(), NOW()),
('ent-course-spring', 'public', 'Spring Boot微服务', 'COURSE', '["Spring","Spring Boot","微服务"]', 'Spring Boot企业级微服务开发', NOW(), NOW()),
('ent-skill-beginner', 'public', '零基础入门', 'SKILL_LEVEL', '["入门","初级","beginner"]', '适合零基础学员', NOW(), NOW()),
('ent-skill-intermediate', 'public', '中级进阶', 'SKILL_LEVEL', '["中级","进阶","intermediate"]', '需要一定编程基础', NOW(), NOW()),
('ent-topic-backend', 'public', '后端开发', 'TOPIC', '["后端","服务端","backend"]', '后端服务开发方向', NOW(), NOW()),
('ent-topic-data', 'public', '数据科学', 'TOPIC', '["数据","数据科学","data"]', '数据分析与AI方向', NOW(), NOW());

-- Seed demo relations
INSERT IGNORE INTO kg_relation (relation_id, tenant_id, source_entity_id, target_entity_id, relation_type, weight, created_at) VALUES
('rel-1', 'public', 'ent-course-java', 'ent-skill-beginner', 'REQUIRES_LEVEL', 1.0, NOW()),
('rel-2', 'public', 'ent-course-java', 'ent-topic-backend', 'BELONGS_TO', 1.0, NOW()),
('rel-3', 'public', 'ent-course-python', 'ent-skill-beginner', 'REQUIRES_LEVEL', 1.0, NOW()),
('rel-4', 'public', 'ent-course-python', 'ent-topic-data', 'BELONGS_TO', 1.0, NOW()),
('rel-5', 'public', 'ent-course-spring', 'ent-skill-intermediate', 'REQUIRES_LEVEL', 1.0, NOW()),
('rel-6', 'public', 'ent-course-spring', 'ent-topic-backend', 'BELONGS_TO', 1.0, NOW()),
('rel-7', 'public', 'ent-course-java', 'ent-course-spring', 'PREREQUISITE_FOR', 0.8, NOW());
