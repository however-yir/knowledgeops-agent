ALTER TABLE api_keys
  ADD COLUMN IF NOT EXISTS expires_at DATETIME NULL,
  ADD COLUMN IF NOT EXISTS revoked_at DATETIME NULL,
  ADD COLUMN IF NOT EXISTS revoked_reason VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS rotated_from_id BIGINT NULL;

CREATE INDEX IF NOT EXISTS idx_api_keys_expire_revoke
  ON api_keys (enabled, expires_at, revoked_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  token_hash VARCHAR(128) NOT NULL UNIQUE,
  principal VARCHAR(255) NOT NULL,
  roles VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_principal
  ON refresh_tokens (principal, expires_at);
