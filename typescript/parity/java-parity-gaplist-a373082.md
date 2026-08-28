# Java parity gap list — oracle re-locked to a373082

> Working evidence for the ts-rewrite backport. Track every gap to its Java
> commit; tick items as their TypeScript mirror lands. Superseded sections of
> this file feed the parity report rewrite at the end of the effort.

## Re-lock context

| field | value |
|---|---|
| previous oracle label | `ac62bb3` (2026-07-21) |
| effective previous tree | pre-2026-06-19 (embedded Java tree predated the 6/19 hardening batch, so the oracle label over-stated coverage) |
| new oracle | `a373082` (2026-08-28) |
| synced paths | `src/`, `pom.xml` — 101 files, +2643/−782 |
| inventory state after re-lock | intentionally red until the backport completes |

## Behavioral gaps (backport work packages)

| # | item | Java commit | TS status |
|---|---|---|---|
| 1 | MCP baseUrl SSRF gate | `1cf29c2` (#145) | ✅ mirrored (`assertSafeMcpEndpoint`, dns + restricted-address classifier + operator allowlist) |
| 2 | rate-limit XFF client IP + bucket hygiene | `a373082` (#146) | ✅ mirrored (`resolveClientIp`, rightmost non-private hop, 50k bucket ceiling, idle eviction timer) |
| 3 | refresh token concurrent reuse | `6f75b32` | ⬜ pending |
| 4 | tenant header override + seeded admin key revocation + JWT/queue/vector paths | `a4f2565` + `84a064d` | ⬜ pending |
| 5 | harness shell/write/trusted runtime default-off | `5b65df9` | ◑ TS defaults already false (stricter than old Java); update manifest javaFragments/relationship to `same` |
| 6 | dependency & container hygiene | `ac62bb3` + `dcf93b7` + `1f8dc8c` | ◑ TS CI already runs pnpm audit / SBOM / Trivy; run and archive current findings |
| 7 | web search backend init hardening | `f841958` | ⬜ pending |
| 8 | per-source hybrid retrieval weights (#115) | `69f9141` | ⬜ pending (new `HybridWeights.java`) |
| 9 | hybrid retrieval flow fix (#137) | `d17ab9d` | ⬜ pending |
| 10 | workspace lifecycle + orphaned streams + step input tokens (#135) | `60a69da` | ⬜ pending (V16 → Prisma optimistic lock) |
| 11 | multi-tenant SQL LIKE escape + ingestion claim | `0c64312` | ⬜ pending (new `SqlLikeUtils.java`) |
| 12 | memory `expires_at` query filter | `d91405b` | ⬜ pending |
| 13 | feedback dataset rotation (#144) | `06c7cb0` | ⬜ pending (`FeedbackProperties.maxDatasetBytes`) |
| 14 | /ai/chat multipart Content-Type fallback (#143) | `a4dc1f1` | ⬜ pending |
| 15 | reliability/tenant-isolation batch | `f112ce7` | ◑ rate-limit eviction mirrored in #2; remainder pending |

Verified N/A:

- `52ba0cb` (register db polling ingestion queue) — the defect is a Spring bean
  registration issue; the TS `IngestionQueueService` selects all backends
  (in-memory / db_polling / redis_stream / rabbitmq) from
  `APP_INGESTION_QUEUE_BACKEND`, so the defect class does not exist.

## Structural gaps (inventory-driven)

Must land for `pnpm inventory:all` to go green against the new oracle:

- **migrations**: `V15__revoke_seeded_demo_api_keys.sql` (TS migration/seed
  change revoking the two publicly committed seed admin credentials),
  `V16__agent_session_state_lock_version.sql` (Prisma schema
  `AgentSessionState.lockVersion` + migration + persistence field map).
- **cross-cutting**: `util/SqlLikeUtils.java` → TS LIKE-escape helper mapping.
- **new Java sources** auto-covered by responsibility groups, TS equivalents
  land with the behavioral items: `retrieval/HybridWeights.java`,
  `service/ReactDecisionParser.java`, `service/ReactResponseFormatter.java`.
- **DTO field maps**: `Result` +`code`/`traceId`/`data` (envelope parity — TS
  error paths already emit `code`), `ReactChatResponseVO` +`fallback`,
  `EvalRunRequestVO` +`datasetId`, `ReactTraceStepVO.getThoughtSummary()`.
- **configuration**: `AgentHarnessProperties` write/shell/trusted → `false`
  and `allowedHosts` (anchor updated for the allowlist key),
  `FeedbackProperties.maxDatasetBytes`, `RagProperties.temperature` +
  `application.yml` `rag.temperature`.
- **routes observed in the Java diff** to verify against the manifest:
  `POST /upload/{chatId}` (multipart), `POST /chat` and `/service`
  text/html variants, `POST /chat/stream` (SSE), audit `latest(limit)`,
  sessions `list(page)`, feedback submit / cost budget update signatures.

## Inventory discipline notes

- Checker order: migration set → configuration sets → cross-cutting set →
  DTO field maps (strict Java ↔ manifest ↔ TS, type families included) →
  production-source responsibility baseline → persistence/migration schema
  vs Prisma physical models.
- The `javaOracle` label is declarative metadata the checker does not
  validate; re-locks must diff the embedded tree against the claimed oracle
  commit from now on.
