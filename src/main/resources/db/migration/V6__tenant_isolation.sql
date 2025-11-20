ALTER TABLE api_keys
  ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant_key_name_active
  ON api_keys (tenant_id, key_name, enabled, revoked_at, expires_at);

ALTER TABLE refresh_tokens
  ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_tenant_principal
  ON refresh_tokens (tenant_id, principal, expires_at);

ALTER TABLE audit_log
  ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX IF NOT EXISTS idx_audit_tenant_created
  ON audit_log (tenant_id, created_at);
