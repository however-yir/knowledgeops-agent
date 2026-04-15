ALTER TABLE api_keys
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_api_keys_tenant_key_name_active
  ON api_keys (tenant_id, key_name, enabled, revoked_at, expires_at);

ALTER TABLE refresh_tokens
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_refresh_tokens_tenant_principal
  ON refresh_tokens (tenant_id, principal, expires_at);

ALTER TABLE audit_log
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_audit_tenant_created
  ON audit_log (tenant_id, created_at);
