from __future__ import annotations

import json
from pathlib import Path


REQUIRED_TAGS = {
    "health",
    "openapi",
    "auth",
    "chat",
    "sse",
    "rag",
    "ingestion",
    "history",
    "sessions",
    "harness",
    "workflow",
    "evaluation",
    "cost",
    "audit",
    "metrics",
    "memory",
    "graph",
    "negative",
}

REQUIRED_FILES = [
    "python/src/knowledgeops_py/app.py",
    "python/tests/test_app.py",
    "python/Dockerfile",
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


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    cases = json.loads((root / "typescript/parity/contract-cases.json").read_text(encoding="utf-8"))
    migration = (root / "python/MIGRATION.md").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/python.yml").read_text(encoding="utf-8") if (root / ".github/workflows/python.yml").exists() else ""
    failures: list[str] = []

    tags = {tag for case in cases for tag in case.get("tags", [])}
    for tag in sorted(REQUIRED_TAGS - tags):
        failures.append(f"contract cases missing tag: {tag}")
    for file_name in REQUIRED_FILES:
        if not (root / file_name).exists():
            failures.append(f"required Python maturity file missing: {file_name}")
    for phrase in REQUIRED_MIGRATION_PHRASES:
        if phrase not in migration:
            failures.append(f"python migration doc missing phrase: {phrase}")
    for command in ["pytest", "knowledgeops-python-contract", "knowledgeops-python-e2e-smoke", "knowledgeops-python-perf-smoke"]:
        if command not in workflow:
            failures.append(f"python CI missing command: {command}")
    if len(cases) < 30:
        failures.append(f"contract case count {len(cases)} is below Python maturity floor 30")

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"python maturity gate ok: {len(cases)} inherited contract cases, {len(REQUIRED_TAGS)} tags")


if __name__ == "__main__":
    main()
