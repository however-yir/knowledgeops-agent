# TypeScript Verification and Parity Report

Date: 2026-08-29
Java oracle baseline: `a3730820090b16548556102c2306a7d7610ec6b4` (2026-08-28)

## Decision

The TypeScript service is a NestJS/Fastify backend with Prisma persistence. This report declares **structural parity with the Java oracle `a373082` plus behavioral parity for the security and feature backport enumerated in `java-parity-gaplist-a373082.md`**. It does not claim full runtime equivalence: the live comparator still depends on externally started, equivalently seeded services, and static inventories establish repository representations, not runtime behavior.

## Backport Evidence (behavioral)

All 13 gap items identified for the 2026-08-28 oracle are closed; per-commit traceability lives in `java-parity-gaplist-a373082.md`. Security alignment matrix:

| Item | Java commit | TypeScript mirror |
|---|---|---|
| MCP baseUrl SSRF gate | `1cf29c2` (#145) | `assertSafeMcpEndpoint` — protocol allowlist, DNS-based restricted-address refusal (loopback/ULA/site-local/link-local/metadata/multicast), operator dot-suffix allowlist, fail-closed resolution |
| Rate-limit proxy-safe client IP | `a373082` (#146) | `resolveClientIp` — XFF parsed only behind private/loopback peers, rightmost non-private hop; 50k bucket ceiling + idle eviction timer |
| Refresh-token concurrent reuse | `6f75b32` | DB-atomic conditional rotation (pre-existing) plus a closed in-memory replay window when Prisma is disabled |
| Tenant header override / seeded admin keys | `a4f2565` | Identity tenant is authoritative with 401 on mismatch (pre-existing, stricter); committed demo ADMIN key no longer materializes in production; forbidden-secret startup guards; compose fallbacks removed |
| Harness shell/write/trusted default-off | `5b65df9` | TypeScript defaults were already off; Java caught up and the manifest anchors record `same` |
| Dependency & container hygiene | `ac62bb3`/`dcf93b7`/`1f8dc8c` | Effective pnpm v10 workspace overrides + 2026-08 advisory wave cleared; audit/SBOM/Trivy gates green |

Feature backport mirrors: per-source hybrid retrieval weights (#115), hybrid retrieval flow (#137), workspace process lifecycle + orphaned stream failure + step input-token persistence (#135), multi-tenant claim/LIKE hardening (0c64312), memory `expires_at` filtering (d91405b), feedback dataset rotation (#144), multipart Content-Type fallback (#143, structurally absent), and the f112ce7 reliability batch (state-machine transition guard, terminal-only queue acks, rethrown synchronous research failures). Items whose defect class does not exist in the TypeScript runtime are marked verified-N/A in the gap list with rationale.

## Contract Evidence

`pnpm inventory:java-baseline` locks the 2026-08-28 Java source baseline's 15 controllers, 49 route declarations, 31 public DTOs, 15 core service responsibilities, 16 security sources, 11 `@ConfigurationProperties` classes, 17 cross-cutting sources, 26 Mapper-to-Prisma-model pairs, and 15 Flyway-to-Prisma migrations to explicit TypeScript sources. Every Java controller is assigned to an explicit TypeScript controller file, and its mapped route fragments must occur in that file; a route may name an explicit target when TypeScript intentionally splits a Java controller across files. The Java security-source set, its TypeScript responsibility anchors, and the TypeScript middleware/guard registration are also checked. Each Java configuration class is assigned key TypeScript environment-variable anchors, and 66 configuration defaults bind a Java field initializer to the exact Zod `.default(...)` expression, classified as the same default, a representation mapping, or a documented intentional difference. All 221 Java production sources must be either individually mapped or contained in one of 12 documented responsibility groups (agent harness/research/workflow, domain, evaluation, graph, ingestion, memory, RAG, repository, retrieval, and service). A responsibility group is source-accounting evidence only: it establishes TypeScript module ownership for related Java adapters, records, interfaces, and helpers, not per-class behavioral equivalence. The inventory checks all 31 baseline DTOs and every declared Java DTO instance field (222 mapped fields), including the documented `thought` to `thoughtSummary` rename; an added, missing, or duplicate Java-field mapping fails the inventory. Each field mapping names the concrete TypeScript interface it targets; Java and TypeScript top-level type families (text, number, boolean, collection, key-value object, unknown value, structured value, or time) must agree. `LocalDateTime` may map to text only when the same mapping declares its ISO-8601 representation; the current baseline records 10 such conversions. For all 25 mapped collection/key-value fields, it also compares collection-element and record key/value type families: 23 match, while 2 documented citation fields intentionally expose TypeScript metadata objects instead of Java citation ID strings. All 22 Java primitive fields must additionally map to required, non-null TypeScript properties. This does not infer reference-field optionality or member-level shapes of nested DTOs. It also derives 25 Java persistence entities and their instance fields from MyBatis `BaseMapper` declarations, requiring each field to exist on the mapped Prisma model; the one custom SQL mapper without a Java entity has a documented exclusion. After applying the Java Flyway baseline in order, it validates 30 physical tables, 294 final columns, their type families (including `VARCHAR` and `DECIMAL` parameters), nullability, explicit defaults, and primary keys, plus 62 named unique/index constraints against Prisma physical representations. `pnpm inventory:implementation-surface` and `pnpm inventory:contracts` additionally check files, TypeScript route fragments, and contract-case representation. These are static checks: they do not call either runtime or compare Java reference-field optionality, member-level nested DTO shape, Spring/Zod binding semantics for maps, lists, aliases, or conditional configuration, authorization behavior, query results, or service behavior. The executable comparator is:

```text
APP_JAVA_BASE_URL=http://java-host APP_TS_BASE_URL=http://ts-host pnpm contract:diff:live
```

It fails when URLs are absent, unreachable, or behavior differs. The workflow does not start Java or run this comparator and therefore makes no automatic live-parity claim.

Java `/v3/api-docs` currently returns 500 because springdoc invokes an incompatible Spring method and raises `NoSuchMethodError`. The endpoint is excluded from the shared comparator as a documented oracle defect, not counted as a TypeScript parity pass. TypeScript `/v3/api-docs`, `/health`, and `/metrics` are covered as TypeScript runtime extensions by `e2e:smoke`.

The `ragproof external quality gate` workflow is ported from the Java tree (dispatch-only, environment-gated) so both runtimes can be evaluated against the same external ragproof baseline, and the nightly regression now includes the evaluator contract fixture steps.

## Executable CI Evidence

| Job | Evidence |
|---|---|
| Quality | frozen install, Prisma generation, typecheck, all-source Vitest coverage, build, Java-baseline and static inventories |
| Database integration | fresh MySQL migration, migration-history check, authenticated concurrent writes, row-count check, API restart, hydration/readback with Prisma enabled |
| Runtime smoke | CI runs performance and bounded load on the freshly migrated MySQL state, then e2e executes the declared contract cases locally with `APP_PRISMA_ENABLED=true` |
| Security and supply chain | canonical npm high/critical audit, Syft CycloneDX SBOM, CycloneDX CLI validation, artifact upload |
| Docker and Compose | Compose model validation, Trivy high/critical configuration scan, final-image startup against MySQL, runtime hardening inspection, auth checks, Trivy high/critical image scan |
| Helm | strict lint, deterministic render, Kubernetes schema validation with kubeconform |

GitHub Actions are pinned to immutable commits. Helm, kubeconform, CycloneDX CLI, Syft, Node, and pnpm versions are pinned; downloaded kubeconform and CycloneDX binaries are checksum-verified.

## Coverage

Coverage includes all production TypeScript source files. The measured 2026-08-29 API baseline is 53.34% lines, 51.19% statements, 50.26% functions, and 36.62% branches — the backport landed with tests, so CI ratchets remain at 40/39/32/24 and no dilution occurred. The shared package enforces 90% lines/statements/functions and 85% branches. The API target is also 90/85; thresholds must rise with new tests and must not be met through fabricated values or broad source exclusions.

## Remaining Gaps

- No automatic Java-vs-TypeScript environment; the live comparator depends on externally started, equivalently seeded services and is not a CI job.
- No browser-level frontend cutover test; only a path inventory exists.
- API coverage (53/51/50/36) remains below the 90/85 target; the ratchet guarantees it rises but reaching the target is a separate engineering effort.
- Static schema evidence does not compare collation, charset, foreign keys, check constraints, seed rows, or query plans.
- Static configuration evidence does not execute Spring or Zod binding for nested maps/lists, aliases, profiles, or conditional values.
- Helm is schema-validated but not installed into a live cluster in this workflow.
- Runtime smoke uses deterministic disabled external LLM/vector/web providers; it does not certify third-party production integrations.

Passing TypeScript CI therefore means the listed TypeScript checks executed successfully, that the TypeScript tree is structurally aligned with Java oracle `a373082`, and that the enumerated security and feature backport landed with tests. It does not mean Java runtime equivalence or production cutover approval.
