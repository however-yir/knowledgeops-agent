# TypeScript Verification and Parity Report

Date: 2026-07-22
Java oracle baseline: `ac62bb3a83239b1b3a8701fcdcad7d337c2c400a`

## Decision

The TypeScript service is a NestJS/Fastify backend with Prisma persistence. This report does not declare Java parity. Static route, table, frontend, and evidence checks are named inventories and establish only that expected repository representations exist.

## Contract Evidence

`pnpm inventory:java-baseline` locks the 2026-07-21 Java source baseline's 15 controllers, 48 route declarations, 31 public DTOs, 15 core service responsibilities, 16 security sources, 11 `@ConfigurationProperties` classes, 26 Mapper-to-Prisma-model pairs, and 13 Flyway-to-Prisma migrations to explicit TypeScript sources. Every Java controller is assigned to an explicit TypeScript controller file, and its mapped route fragments must occur in that file; a route may name an explicit target when TypeScript intentionally splits a Java controller across files. The Java security-source set, its TypeScript responsibility anchors, and the TypeScript middleware/guard registration are also checked. Each Java configuration class is assigned key TypeScript environment-variable anchors. It checks all 31 baseline DTOs and 217 key fields, including the documented `thought` to `thoughtSummary` rename and time-value representations. It also derives 25 Java persistence entities and their instance fields from MyBatis `BaseMapper` declarations, requiring each field to exist on the mapped Prisma model; the one custom SQL mapper without a Java entity has a documented exclusion. The Java Flyway baseline's 30 physical tables and 290 created or added columns must also have Prisma `@@map` and `@map` physical representations. `pnpm inventory:implementation-surface` and `pnpm inventory:contracts` additionally check files, TypeScript route fragments, and contract-case representation. These are static checks: they do not call either runtime or compare DTO optionality, nested shape, database types, nullability, defaults, indexes, configuration defaults or nested binding semantics, authorization behavior, query results, or service behavior. The executable comparator is:

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
- Helm is schema-validated but not installed into a live cluster in this workflow.
- Runtime smoke uses deterministic disabled external LLM/vector/web providers; it does not certify third-party production integrations.

Passing TypeScript CI therefore means the listed TypeScript checks executed successfully. It does not mean Java maturity equivalence or production cutover approval.
