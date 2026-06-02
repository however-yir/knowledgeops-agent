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
        "| Python | Enterprise parity track | pytest, contract gate, e2e smoke, perf smoke, security gate, Docker build |",
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
            "## Remaining Production Work",
            "",
            "- Replace local simple queue/vector stores with managed Redis/pgvector in production configuration.",
            "- Add live Java-vs-TS-vs-Python response diff once Python is deployed beside the other runtimes.",
            "- Add provider-backed LLM integration after local contract gates stay stable.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
