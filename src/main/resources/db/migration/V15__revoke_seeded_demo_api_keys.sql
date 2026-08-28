-- Revoke publicly-known seeded ADMIN API keys.
-- V7 seeded a never-expiring ADMIN tenant key whose plaintext ("dev-admin-key-2026")
-- is committed to the repository, and V1 seeded a dev-default ADMIN key
-- ("dev-default-admin-key"). Any deployment that ran those migrations carries
-- credentials that are effectively public. V1/V7 themselves must stay untouched
-- (Flyway checksum stability), so this migration disables both rows; real admin
-- credentials must be issued explicitly via the /auth/api-keys API or ops tooling.
UPDATE api_keys
   SET enabled = 0,
       revoked_at = NOW(),
       revoked_reason = 'revoked by V15: publicly committed seed credential',
       updated_at = NOW()
 WHERE key_hash IN (
       '1c39ba1a74432335b91233cd2ac43151b22ccbbeb490916c5293de7f3f41435e',
       '6cbae51c7775b973f845b3fb4b333495890ecc9c57a9c3b3d662a3200d3227e1'
    )
    OR key_name IN ('demo-admin-key-2026', 'dev-default-admin-key');
