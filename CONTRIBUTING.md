# Contributing

Thanks for contributing.

## Development Setup
1. Install JDK 17+
2. Install Maven 3.9+
3. Run build locally:
   - `mvn -B -ntp verify`

## Pull Request Checklist
- Keep PRs focused and small
- Update docs when behavior or usage changes
- Ensure CI passes
- Avoid committing generated artifacts (`target/`, build bundles, logs)

## Commit Style
Prefer clear, scoped commit messages, for example:
- `feat: add xxx`
- `fix: handle xxx edge case`
- `chore: update docs/ci`
