# TypeScript Migration Evidence

Java remains the production oracle while the TypeScript implementation grows under `typescript/`. The read-only baseline used for this checkpoint is Java commit `ac62bb3a83239b1b3a8701fcdcad7d337c2c400a` from 2026-07-21.

## Evidence Status

| Area | TypeScript evidence | Current claim |
|---|---|---|
| Configuration and API implementation | typecheck, build, Vitest, Java-baseline inventory (15 controller sources, 48 route declarations), implementation and contract inventories | Implemented and locally tested; static mapping is non-parity |
| Security and tenant boundary | auth/tenant unit tests plus final-image auth and container-hardening smoke | Executed TypeScript evidence, not Java equivalence |
| Database mapping | Prisma table inventory | Static mapping inventory only |
| Database behavior | fresh `prisma migrate deploy`, concurrent session writes, MySQL row check, process restart and hydration with `APP_PRISMA_ENABLED=true` | Executed integration evidence |
| Runtime API behavior | e2e executes all 37 declared contract cases in local fallback mode; CI also runs e2e, performance, and bounded load with Prisma explicitly enabled | Executed TypeScript smoke evidence, not Java equivalence |
| Frontend cutover | frontend path-string inventory | Static inventory only; no browser or live frontend test |
| Packaging | Compose model validation, final-image startup, non-root/read-only/capability checks, Trivy scan | Executed deployment evidence |
| Kubernetes | Helm strict lint, deterministic template, kubeconform validation | Render-time evidence; no live cluster rollout |
| Supply chain | canonical npm audit, Syft CycloneDX generation, CycloneDX CLI validation, artifact upload | Executed CI evidence |
| Java-vs-TypeScript contract | `contract:diff:live` against two externally started services | Executable only when both running service URLs are supplied; not part of CI evidence |

The `inventory:*` commands intentionally report representation, not equivalence. Their success must never be summarized as Java runtime parity, migration readiness, frontend compatibility, production maturity, or security enforcement.

## Coverage Ratchet

Coverage includes every production `src/**/*.ts` file. The shared package enforces the 90% lines/statements/functions and 85% branches target. The API measured baseline on 2026-07-22 is 40.00% lines, 39.02% statements, 32.50% functions, and 24.06% branches; CI floors are 40/39/32/24. Increase the floors whenever tests raise the measured baseline. Reaching 90/85 requires tests for currently uncovered controllers, workers, middleware, bootstrap paths, external clients, and persistence branches; no synthetic exclusions or fabricated values are used.

## Cutover And Rollback

1. Start Java and TypeScript against isolated staging databases migrated from the same production snapshot.
2. Run the TypeScript fresh-migration and persistence gate with `APP_PRISMA_ENABLED=true`; a static table inventory is not a substitute.
3. Start both services and run `APP_JAVA_BASE_URL=http://java-host APP_TS_BASE_URL=http://ts-host pnpm contract:diff:live`. Missing or unreachable URLs fail the command.
4. Send shadow read traffic to TypeScript and compare status, content type, JSON schema, SSE events, authorization decisions, pagination, and latency.
5. Verify backup/restore and rollback to Java before moving authoritative traffic. Keep Java schema-compatible until the observation window closes.
6. Use dual-write only for explicitly reviewed append-safe tables, with reconciliation and failure handling, before considering authoritative TypeScript writes.
7. Promote only after live contract, data, security, frontend, performance, and operational acceptance evidence is recorded for the release candidate.

## Live Contract Boundaries

The workflow does not start Java or run the live comparator, so it does not claim automatic live parity. Run `contract:diff:live` only against externally started, equivalently seeded Java and TypeScript services. Both URLs are mandatory; absent URLs, unreachable services, and mismatches fail. Set `APP_CONTRACT_API_KEY` when both services require a shared key.

The Java oracle currently returns 500 for `/v3/api-docs` because springdoc invokes an incompatible Spring method and raises `NoSuchMethodError`. This known oracle defect is excluded from the shared live cases and is not represented as a TypeScript parity success. The TypeScript OpenAPI route and TypeScript-only `/health` and `/metrics` aliases are exercised separately by `e2e:smoke`.
