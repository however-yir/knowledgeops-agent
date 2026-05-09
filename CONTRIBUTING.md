# Contributing

Thanks for your interest in improving KnowledgeOps Agent!

## Getting Started

### Prerequisites

- JDK 17+
- Maven 3.9+
- Node.js 18+ (for frontend)
- Docker & Docker Compose (for infra services)

### Backend Setup

```bash
# Run tests
mvn -B -ntp test

# Full verification (includes static analysis, coverage, dependency check)
mvn -B -ntp verify

# Quick compile
mvn -B -ntp compile
```

### Frontend Setup

```bash
cd frontend
npm install
npm run build        # production build
npm run lint         # ESLint check
```

### Full Stack (Docker)

```bash
./scripts/demo.sh
```

## Branch and Commit

- Branch from `main`
- Keep commits small and focused
- Use conventional commit style:
  - `feat: ...` — new feature
  - `fix: ...` — bug fix
  - `docs: ...` — documentation only
  - `refactor: ...` — code change that neither fixes a bug nor adds a feature
  - `chore: ...` — tooling, CI, dependency updates
  - `test: ...` — adding or updating tests

## Pull Request Guidelines

- Keep each PR scoped to one change set
- Add or update tests when behavior changes
- Update docs when API/config/usage changes
- Ensure `mvn -B -ntp verify` passes before requesting review
- Run `cd frontend && npm run build && npm run lint` for frontend changes
- Do not commit generated/runtime artifacts (`target/`, `node_modules/`, logs, local env files)

## Code Style

- **Java**: Follow existing conventions; Checkstyle, PMD, and SpotBugs are enforced in CI
- **TypeScript/Vue**: ESLint + Prettier config in `frontend/`; run `npm run lint` before committing
- Avoid unrelated refactors in feature/fix PRs
- Prefer clear naming and small methods over clever shortcuts

## Reporting Issues

- Use the [bug report template](https://github.com/however-yir/knowledgeops-agent/issues/new?template=bug_report.yml) for reproducible problems
- Use the [feature request template](https://github.com/however-yir/knowledgeops-agent/issues/new?template=feature_request.yml) for suggestions
- For security vulnerabilities, see [SECURITY.md](SECURITY.md) — do **not** open public issues

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you agree to uphold this code.
