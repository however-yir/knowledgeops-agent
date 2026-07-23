# TypeScript Verification and Parity Report

Date: 2026-07-22
Java oracle baseline: `ac62bb3a83239b1b3a8701fcdcad7d337c2c400a`

## Decision

The TypeScript service is a NestJS/Fastify backend with Prisma persistence. This report does not declare Java parity. Static route, table, frontend, and evidence checks are named inventories and establish only that expected repository representations exist.

## Contract Evidence

`pnpm inventory:java-baseline` locks the 2026-07-21 Java source baseline's 15 controllers, 48 route declarations, 31 public DTOs, 15 core service responsibilities, 16 security sources, 11 `@ConfigurationProperties` classes, 16 cross-cutting sources, 26 Mapper-to-Prisma-model pairs, and 13 Flyway-to-Prisma migrations to explicit TypeScript sources. Every Java controller is assigned to an explicit TypeScript controller file, and its mapped route fragments must occur in that file; a route may name an explicit target when TypeScript intentionally splits a Java controller across files. The Java security-source set, its TypeScript responsibility anchors, and the TypeScript middleware/guard registration are also checked. Each Java configuration class is assigned key TypeScript environment-variable anchors. All 65 such anchors also bind a Java field initializer to the exact Zod `.default(...)` expression and classify the relation as the same default, a representation mapping, or a documented intentional difference. The cross-cutting source set covers application bootstrap, startup validation, common, CORS, queue, chat-memory, OpenAPI, resilience, security-header, and vector configuration; global exception handling; customer-service tools; conversation IDs; hashing; and vector distance. Finally, all 217 Java production sources must be either individually mapped or contained in one of 12 documented responsibility groups (agent harness/research/workflow, domain, evaluation, graph, ingestion, memory, RAG, repository, retrieval, and service). A responsibility group is source-accounting evidence only: it establishes TypeScript module ownership for related Java adapters, records, interfaces, and helpers, not per-class behavioral equivalence. It checks all 31 baseline DTOs and 217 key fields, including the documented `thought` to `thoughtSummary` rename. Each field mapping names the concrete TypeScript interface it targets; Java and TypeScript top-level type families (text, number, boolean, collection, key-value object, unknown value, structured value, or time) must agree. `LocalDateTime` may map to text only when the same mapping declares its ISO-8601 representation; the current baseline records 10 such conversions. For all 25 mapped collection/key-value fields, it also compares collection-element and record key/value type families: 23 match, while 2 documented citation fields intentionally expose TypeScript metadata objects instead of Java citation ID strings. This does not infer optionality or member-level shapes of nested DTOs. It also derives 25 Java persistence entities and their instance fields from MyBatis `BaseMapper` declarations, requiring each field to exist on the mapped Prisma model; the one custom SQL mapper without a Java entity has a documented exclusion. After applying the Java Flyway baseline in order, it validates 30 physical tables, 293 final columns, their type families (including `VARCHAR` and `DECIMAL` parameters), nullability, explicit defaults, and primary keys, plus 62 named unique/index constraints against Prisma physical representations. `pnpm inventory:implementation-surface` and `pnpm inventory:contracts` additionally check files, TypeScript route fragments, and contract-case representation. These are static checks: they do not call either runtime or compare DTO optionality, member-level nested DTO shape, Spring/Zod binding semantics for maps, lists, aliases, or conditional configuration, authorization behavior, query results, or service behavior. The executable comparator is:

```text
APP_JAVA_BASE_URL=http://java-host APP_TS_BASE_URL=http://ts-host pnpm contract:diff:live
```

It fails when URLs are absent, unreachable, or behavior differs. The workflow does not start Java or run this comparator and therefore makes no automatic live-parity claim.

Java `/v3/api-docs` currently returns 500 because springdoc invokes an incompatible Spring method and raises `NoSuchMethodError`. The endpoint is excluded from the shared comparator as a documented oracle defect, not counted as a TypeScript parity pass. TypeScript `/v3/api-docs`, `/health`, and `/metrics` are covered as TypeScript runtime extensions by `e2e:smoke`.

## Executable CI Evidence

| Job | Evidence |
|---|---|
| Quality | frozen install, Prisma generation, typecheck, all-source Vitest coverage, build, Java-baseline and static inventories |
| Database integration | fresh MySQL migration, migration-history check, authenticated concurrent writes, row-count check, API restart, hydration/readback with Prisma enabled |
| Runtime smoke | CI runs performance and bounded load on the freshly migrated MySQL state, then e2e executes all 37 declared contract cases locally with `APP_PRISMA_ENABLED=true` |
| Security and supply chain | canonical npm high/critical audit, Syft CycloneDX SBOM, CycloneDX CLI validation, artifact upload |
| Docker and Compose | Compose model validation, Trivy high/critical configuration scan, final-image startup against MySQL, runtime hardening inspection, auth checks, Trivy high/critical image scan |
| Helm | strict lint, deterministic render, Kubernetes schema validation with kubeconform |

GitHub Actions are pinned to immutable commits. Helm, kubeconform, CycloneDX CLI, Syft, Node, and pnpm versions are pinned; downloaded kubeconform and CycloneDX binaries are checksum-verified.

## Coverage

Coverage includes all production TypeScript source files. The measured 2026-07-22 API baseline is 40.00% lines, 39.02% statements, 32.50% functions, and 24.06% branches, so CI ratchets at 40/39/32/24. The shared package enforces 90% lines/statements/functions and 85% branches. The API target is also 90/85; thresholds must rise with new tests and must not be met through fabricated values or broad source exclusions.

## Remaining Gaps

- No automatic Java-vs-TypeScript environment; the live comparator depends on externally started, equivalently seeded services and is not a CI job.
- No browser-level frontend cutover test; only a path inventory exists.
- Static schema evidence does not compare collation, charset, foreign keys, check constraints, seed rows, or query plans.
- Static configuration evidence does not execute Spring or Zod binding for nested maps/lists, aliases, profiles, or conditional values.
- Helm is schema-validated but not installed into a live cluster in this workflow.
- Runtime smoke uses deterministic disabled external LLM/vector/web providers; it does not certify third-party production integrations.

Passing TypeScript CI therefore means the listed TypeScript checks executed successfully. It does not mean Java maturity equivalence or production cutover approval.
