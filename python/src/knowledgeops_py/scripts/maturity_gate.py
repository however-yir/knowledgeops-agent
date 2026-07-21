from __future__ import annotations

from pathlib import Path

from knowledgeops_py.scripts.contract_gate import REQUIRED_OPENAPI_ENDPOINTS

REQUIRED_FILES = [
    "python/src/knowledgeops_py/app.py",
    "python/src/knowledgeops_py/dto.py",
    "python/src/knowledgeops_py/domain/context.py",
    "python/src/knowledgeops_py/domain/ports.py",
    "python/src/knowledgeops_py/infrastructure/models.py",
    "python/src/knowledgeops_py/infrastructure/database.py",
    "python/src/knowledgeops_py/infrastructure/queues.py",
    "python/src/knowledgeops_py/infrastructure/providers.py",
    "python/src/knowledgeops_py/workers/runner.py",
    "python/src/knowledgeops_py/scripts/contract_gate.py",
    "python/src/knowledgeops_py/scripts/java_baseline_manifest.py",
    "python/src/knowledgeops_py/scripts/manifest_gate.py",
    "python/src/knowledgeops_py/scripts/security_gate.py",
    "python/src/knowledgeops_py/scripts/parity_report.py",
    "python/tests/test_app.py",
    "python/Dockerfile",
    "python/alembic/versions/0001_java_v14_baseline.py",
    "python/parity/java-baseline-manifest.json",
    "python/helm/knowledgeops-python/templates/workloads.yaml",
    ".github/workflows/python.yml",
]

REQUIRED_MIGRATION_PHRASES = [
    "Maturity Equivalence Gate",
    "API contract",
    "security and tenant boundary",
    "data persistence",
    "observability and performance",
    "rollback",
]

REQUIRED_CI_COMMANDS = [
    "pytest",
    "knowledgeops-python-contract",
    "knowledgeops-python-security-gate",
    "knowledgeops-python-maturity",
    "knowledgeops-python-e2e-smoke",
    "knowledgeops-python-perf-smoke",
    "knowledgeops-python-parity-report",
    "knowledgeops-python-manifest-gate",
    "ruff check",
    "mypy",
    "bandit",
    "pip-audit",
    "alembic upgrade",
]


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    migration = (root / "python/MIGRATION.md").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/python.yml").read_text(encoding="utf-8") if (root / ".github/workflows/python.yml").exists() else ""
    failures: list[str] = []

    for file_name in REQUIRED_FILES:
        if not (root / file_name).exists():
            failures.append(f"required Python maturity file missing: {file_name}")
    for phrase in REQUIRED_MIGRATION_PHRASES:
        if phrase not in migration:
            failures.append(f"python migration doc missing phrase: {phrase}")
    for command in REQUIRED_CI_COMMANDS:
        if command not in workflow:
            failures.append(f"python CI missing command: {command}")
    if len(REQUIRED_OPENAPI_ENDPOINTS) < 24:
        failures.append("Python enterprise contract endpoint floor not met")

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"python enterprise maturity gate ok: {len(REQUIRED_OPENAPI_ENDPOINTS)} fixed endpoints, {len(REQUIRED_CI_COMMANDS)} CI commands")


if __name__ == "__main__":
    main()
