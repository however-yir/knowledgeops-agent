# Python Rewrite Migration and Cutover

## Fixed baseline

The Java reference is `ac62bb3a83239b1b3a8701fcdcad7d337c2c400a`. Its controller routes, Flyway V1–V14 files, discovered tables and SSE event names are committed in `parity/java-baseline-manifest.json`. Regenerate it only from an isolated checkout of that SHA:

```bash
git worktree add --detach /tmp/knowledgeops-java ac62bb3a83239b1b3a8701fcdcad7d337c2c400a
knowledgeops-python-baseline-manifest \
  --repository /tmp/knowledgeops-java \
  --revision ac62bb3a83239b1b3a8701fcdcad7d337c2c400a \
  --output parity/java-baseline-manifest.json
```

## Maturity Equivalence Gate

| Gate | Evidence |
|---|---|
| API contract | `knowledgeops-python-contract` checks canonical routes, Java-shaped envelopes, SSE events and the `/python/v1` compatibility adapter. |
| security and tenant boundary | Tests cover API Key administration, JWT rotation, tenant-header consistency, IDOR rejection, confirmation-token binding and production startup validation. |
| data persistence | Alembic revision `0001_java_v14_baseline` creates additive Python state tables. Java Flyway remains the owner of shared production schema during shadow mode. |
| observability and performance | JSON logging, OTel trace context, native `/actuator/prometheus`, health probes, E2E and performance gates are part of CI. |
| rollback | API routing returns to Java and Java workers resume; Python tables are additive and are never required for Java reads. |

## Deployment modes

- `APP_ENV=development` allows the deterministic memory queue and local test key.
- `APP_ENV=production` requires an explicit JWT secret, non-demo API key, database URL, Redis URL and non-identity reranker.
- Run `knowledgeops-python-api` and `knowledgeops-python-worker` from the same image. Use `docker compose -f docker-compose.yml -f docker-compose.python.yml up` for the local dependency stack.
- OIDC needs issuer, client ID and redirect URI. Callback exchange verifies discovery metadata, JWKS, issuer, audience, nonce and a PKCE verifier before it issues a one-time local exchange code.

## Shadow and cutover procedure

1. Run migrations only in an isolated Python database, replay desensitized requests, and save contract/performance reports.
   Use `knowledgeops-python-cross-contract --java-base-url ... --python-base-url ... --api-key ... --tenant-id ...` against the two isolated stacks.
   Before the replay, run `knowledgeops-python-shadow-preflight`. It verifies production dependencies, OIDC settings, queue selection, isolated-write declarations and the 10,000-request-or-7-day observation target without printing secrets or calling external services.
2. Mirror read-only production traffic to Python. Mirror writes only into the isolated database.
3. Require 10,000 requests or seven continuous days with structure difference `<0.5%`, no cross-tenant result, error rate within `0.2` percentage points of Java and p95 no more than `1.2x` Java.
   Export only desensitized aggregate measurements as JSON and run `knowledgeops-python-shadow-evidence --evidence shadow-metrics.json`; it prints a machine-readable accepted/rejected decision and never reads raw request payloads.
   The evidence file contains counts and decimal rates only, for example:

   ```json
   {
     "requestCount": 10000,
     "continuousDays": 0,
     "structureDifferenceRate": 0.004,
     "javaErrorRate": 0.01,
     "pythonErrorRate": 0.012,
     "javaP95Ms": 500,
     "pythonP95Ms": 600,
     "crossTenantErrors": 0
   }
   ```
4. Drain Java workers, stamp the compatible Alembic revision, start Python workers, then direct write traffic to Python.
5. On any breach, route back to Java and restart Java workers. Do not run destructive Python migrations during rollback.
