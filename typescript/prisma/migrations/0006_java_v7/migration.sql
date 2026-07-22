INSERT IGNORE INTO api_keys (
  key_hash,
  key_name,
  tenant_id,
  role_name,
  enabled,
  created_at,
  updated_at
) VALUES (
  '1c39ba1a74432335b91233cd2ac43151b22ccbbeb490916c5293de7f3f41435e',
  'demo-admin-key-2026',
  'public',
  'ADMIN',
  1,
  NOW(),
  NOW()
);
