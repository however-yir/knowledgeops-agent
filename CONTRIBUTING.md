# Contributing

Thanks for your interest in improving `Intelligent Q&A and Knowledge Retrieval Platform`.

## Development Setup
1. Install JDK 17+
2. Install Maven 3.9+
3. Start required services if your change depends on infra (MySQL/Redis/RabbitMQ)
4. Validate locally:
   - `mvn -B -ntp test`
   - `mvn -B -ntp verify`

## Branch and Commit
- Branch from `main`
- Keep commits small and focused
- Prefer conventional commit style:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `chore: ...`

## Pull Request Guidelines
- Keep each PR scoped to one change set
- Add or update tests when behavior changes
- Update docs when API/config/usage changes
- Ensure CI is green before requesting review
- Do not commit generated/runtime artifacts (`target/`, logs, local env files)

## Code Style
- Follow existing project conventions
- Avoid unrelated refactors in feature/fix PRs
- Prefer clear naming and small methods over clever shortcuts
