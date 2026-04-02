INSERT IGNORE INTO permissions (id, permission_name, created_at) VALUES
  (5, 'auth:key_manage', NOW()),
  (6, 'rag:read', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at) VALUES
  (1, 5, NOW()),
  (1, 6, NOW()),
  (2, 6, NOW()),
  (3, 4, NOW());
