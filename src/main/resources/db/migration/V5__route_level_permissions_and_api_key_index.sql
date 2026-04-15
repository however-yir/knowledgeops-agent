CREATE INDEX idx_api_keys_key_name_active
  ON api_keys (key_name, enabled, revoked_at, expires_at);

INSERT IGNORE INTO permissions (permission_name, created_at) VALUES
  ('chat:read', NOW()),
  ('ingestion:read', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at)
SELECT r.id, p.id, NOW()
FROM roles r
INNER JOIN permissions p ON (
  (r.role_name = 'ADMIN' AND p.permission_name IN ('chat:read', 'ingestion:read'))
  OR (r.role_name = 'USER' AND p.permission_name IN ('chat:read', 'ingestion:read', 'rag:read'))
  OR (r.role_name = 'OPS' AND p.permission_name IN ('ingestion:read', 'metrics:read', 'audit:read'))
);
