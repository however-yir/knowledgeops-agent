INSERT IGNORE INTO permissions (permission_name, created_at) VALUES
  ('agent:trusted', NOW());

INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at)
SELECT r.id, p.id, NOW()
FROM roles r
INNER JOIN permissions p ON (
  r.role_name = 'ADMIN' AND p.permission_name = 'agent:trusted'
);
