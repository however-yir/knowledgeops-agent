# KnowledgeOps Agent Evidence Pack

This pack collects the shortest public proof path for reviewing the project as a runnable AI platform.

## Runtime Evidence

- Local proof path: `./scripts/demo.sh`
- Pullable image: `docker pull ghcr.io/however-yir/knowledgeops-agent:latest`
- Container workflow: `.github/workflows/publish-image.yml`
- Main CI: `.github/workflows/ci.yml`
- Regression workflow: `.github/workflows/nightly-regression.yml`
- Baseline release: `AI Matrix Baseline 2026.05`
- Release: `v1.0.0 - Enterprise-ready KnowledgeOps Agent`

## Product And Architecture Evidence

- Demo GIF: `docs/assets/screenshots/demo.gif`
- RAG citations screenshot: `docs/assets/rag-answer-citations.png`
- Architecture overview: `docs/assets/architecture-overview.svg`
- Workflow architecture: `docs/architecture-agent-workflow.md`
- Hybrid retrieval architecture: `docs/architecture-hybrid-retrieval.md`
- Knowledge graph architecture: `docs/architecture-knowledge-graph.md`
- Memory system architecture: `docs/architecture-memory-system.md`

## Verification Checklist

- Start the demo stack from a clean checkout.
- Upload or seed a knowledge document.
- Run a RAG answer and confirm citations/evidence are returned.
- Run an Agent workflow and confirm task/step/event state is visible.
- Check Prometheus/Grafana/trace documentation in `docs/observability.md`.
- Open the latest GitHub Actions run and confirm the baseline CI is green.
