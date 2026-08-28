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
| 3 | refresh token concurrent reuse | `6f75b32` | ✅ Prisma path was already conditional-atomic; closed a real concurrent-replay window in the in-memory mode (persistence injected + Prisma disabled skipped the `Map.delete` gate across an await boundary) |
| 4 | tenant header override + seeded admin key revocation + JWT/queue/vector paths | `a4f2565` + `84a064d` | ✅ H1 verified already closed (TS is stricter: mismatched tenant header ⇒ 401); seeded demo ADMIN key no longer materializes in production; forbidden-secret startup guards added; M1 (JWT 401 fallback) verified closed via `parseJwt` internal catch; M2 holds by construction (NestJS method decorators); queue/vector reliability sub-items tracked under item 15 |
| 5 | harness shell/write/trusted runtime default-off | `5b65df9` | ✅ TS defaults already false (stricter than old Java); manifest javaFragments/relationship updated to `same` where Java caught up |
| 6 | dependency & container hygiene | `ac62bb3` + `dcf93b7` + `1f8dc8c` | ✅ overrides restored to effective scope (pnpm v10 workspace root) + 2026-08 advisory wave cleared; `security:audit` gate green |
| 7 | web search backend init hardening | `f841958` | ✅ verified structurally absent in TS (per-call fetch with `AbortSignal.timeout`, no shared lazily-initialized client); frontend DOMPurify/noopener fixes live on the Java tree's frontend, no TS frontend to patch |
| 8 | per-source hybrid retrieval weights (#115) | `69f9141` | ✅ mirrored (`ai/hybrid-weights.ts` presets + normalize; `hybridRetrieve`/`hybridRetrieveAsync` accept weights, DEFAULT preset equals the previous hardcoded 0.4/0.25/0.2/0.15) |
| 9 | hybrid retrieval flow fix (#137) | `d17ab9d` | ✅ verified N/A — the removed Java block was a conflict-artifact duplicate; TS fusion is single-path |
| 10 | workspace lifecycle + orphaned streams + step input tokens (#135) | `60a69da` | ⬜ pending (V16 → Prisma optimistic lock) |
| 11 | multi-tenant SQL LIKE escape + ingestion claim | `0c64312` | ✅ verified equivalent — TS builds no SQL LIKE patterns (in-memory scoring, no raw SQL) and `claim` is strictly tenant-scoped with lease tokens |
| 12 | memory `expires_at` query filter | `d91405b` | ✅ verified already filtered — both memory read endpoints (items list, context) exclude expired items; no RAG memory-injection path exists |
| 13 | feedback dataset rotation (#144) | `06c7cb0` | ✅ mirrored (`APP_FEEDBACK_MAX_DATASET_BYTES` 50 MiB cap + timestamped sibling rotation before append) |
| 14 | /ai/chat multipart Content-Type fallback (#143) | `a4dc1f1` | ✅ verified N/A — the only TS multipart consumer (ingestion upload) never parses mimetype; a missing Content-Type degrades gracefully |
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
