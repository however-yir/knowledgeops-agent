ALTER TABLE api_keys
  ADD COLUMN expires_at DATETIME NULL,
  ADD COLUMN revoked_at DATETIME NULL,
  ADD COLUMN revoked_reason VARCHAR(255) NULL,
  ADD COLUMN rotated_from_id BIGINT NULL;

CREATE INDEX idx_api_keys_expire_revoke
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

CREATE INDEX idx_refresh_tokens_principal
  ON refresh_tokens (principal, expires_at);
