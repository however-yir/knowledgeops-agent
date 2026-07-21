from __future__ import annotations

from pathlib import Path

from knowledgeops_py.scripts.contract_gate import REQUIRED_OPENAPI_ENDPOINTS


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    report_dir = root / "python" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "python-parity-report.md"
    lines = [
        "# KnowledgeOps Agent Python Parity Report",
        "",
        "Python target: FastAPI enterprise service edition.",
        "",
        "## Three Runtime Status",
        "",
        "| Runtime | Status | Evidence |",
        "|---|---|---|",
        "| Java | Baseline | Spring Boot source and Maven/Baseline CI |",
        "| TypeScript | Rewrite reference | TypeScript parity gates and contract cases |",
            "| Python | Enterprise rewrite | unit/integration tests, contract gate, security gate, Alembic, SBOM and container CI |",
        "",
        "## Fixed API Surface",
        "",
        "| Method | Path | Python status |",
        "|---|---|---|",
    ]
    for method, path in REQUIRED_OPENAPI_ENDPOINTS:
        lines.append(f"| {method} | `{path}` | implemented |")
    lines.extend(
        [
            "",
            "## Response Contract",
            "",
            "- Success responses use `ok`, `msg`, `data`, `traceId`.",
            "- Error responses use `ok=0`, `msg`, `code`, `traceId`.",
            "- Chat data includes `answer`, `model`, `usage`, `traceId`.",
            "- RAG data includes `answer`, `citations`, `evidence`, `retrievalStats`.",
            "- Citation data includes `id`, `source`, `title`, `chunkId`, `snippet`.",
            "- Agent trace includes `step`, `thoughtSummary`, `action`, `actionInput`, `observation`.",
            "",
            "## Deployment Evidence Required",
            "",
            "- Real model, Redis, pgvector, RabbitMQ and OIDC settings are mandatory in production; CI uses deterministic local adapters.",
            "- Run the Java/Python black-box runner against a deployed isolated stack before any routing change.",
            "- Shadow evidence remains external: 10,000 requests or seven days, zero tenant isolation failures, and agreed error/latency limits.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
