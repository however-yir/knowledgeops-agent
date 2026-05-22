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
- RAG Evaluation Studio screenshot: `docs/assets/evaluation-report-studio.png`
- RAG citations screenshot: `docs/assets/rag-answer-citations.png`
- Architecture overview: `docs/assets/architecture-overview.svg`
- Workflow architecture: `docs/architecture-agent-workflow.md`
- Hybrid retrieval architecture: `docs/architecture-hybrid-retrieval.md`
- Knowledge graph architecture: `docs/architecture-knowledge-graph.md`
- Memory system architecture: `docs/architecture-memory-system.md`

## RAG Evaluation Reproduction

The Evaluation Studio path uses the platform API and the existing Hybrid RAG chain. It persists `eval_dataset`, `eval_case`, `eval_run`, and `eval_result`, then exports one latest report file.

```bash
# 1. Start the local stack
make demo

# 2. Generate the latest evaluation report
make eval-demo

# 3. Inspect the report
open evaluation/reports/latest-evaluation-report.md
```

API path behind the demo:

1. `POST /ai/evaluation/datasets`
2. `POST /ai/evaluation/datasets/{datasetId}/runs`
3. `GET /ai/evaluation/datasets/{datasetId}/comparison`
4. `GET /ai/evaluation/runs/{runId}/report`

Dashboard path:

- Open `http://localhost:8088`
- Switch to `Evaluation`
- Compare baseline vs current metrics: retrieval hit rate, citation coverage, answer faithfulness, average latency, failure rate, run score.

## Cross-Repo Integration Evidence (KnowledgeOps → tianji)

The following evidence demonstrates that the "KnowledgeOps→tianji" matrix link is a runnable code path, not just a README arrow.

### Prerequisites

```bash
# 1. Start KnowledgeOps Agent stack
cd knowledgeops-agent && ./scripts/demo.sh

# 2. Start tianji-ai-agent stack (in another terminal)
cd tianji-ai-agent && bash scripts/quick-start-mac.sh

# 3. Set cross-repo environment variables for tianji
export TJ_AI_KNOWLEDGEOPS_ENABLED=true
export TJ_AI_KNOWLEDGEOPS_BASE_URL=http://localhost:8080
export TJ_AI_KNOWLEDGEOPS_API_KEY=your-api-key
```

### Verification Steps

1. **Web Retrieval is functional**: With `APP_WEB_SEARCH_ENABLED=true` and a SearXNG instance configured, send a research query → confirm `retrieval.web.latency` metric shows `outcome=success` (not `disabled` or `no-backend`).
2. **KnowledgeOpsClient reaches KnowledgeOps**: With `TJ_AI_KNOWLEDGEOPS_ENABLED=true` in tianji, send a KNOWLEDGE or RECOMMEND prompt → check tianji logs for `KnowledgeOps platform RAG` or `KnowledgeOps platform memory` enrichment messages.
3. **Fallback works**: With `TJ_AI_KNOWLEDGEOPS_ENABLED=false`, send the same prompt → tianji's KnowledgeAgent and RecommendAgent fall back to local VectorStore Advisor without errors.
4. **Both CIs are green**: Open the latest GitHub Actions run for both repositories and confirm `✓` on main branch pushes.

### Cross-Repo Docker Compose (Minimal)

```yaml
# docker-compose.cross-repo.yml — for local cross-repo verification
version: "3.8"
services:
  searxng:
    image: searxng/searxng:latest
    ports: ["8888:8080"]
    environment:
      SEARXNG_BASE_URL: http://localhost:8888/

  knowledgeops:
    image: ghcr.io/however-yir/knowledgeops-agent:latest
    ports: ["8080:8080"]
    environment:
      SPRING_PROFILES_ACTIVE: dev
      APP_WEB_SEARCH_ENABLED: "true"
      APP_WEB_SEARCH_BACKEND: searxng
      APP_WEB_SEARCH_SEARXNG_URL: http://searxng:8080
    depends_on: [searxng]

  tianji-aigc:
    image: ghcr.io/however-yir/tianji-ai-agent:demo
    ports: ["8094:8094"]
    environment:
      TJ_AI_KNOWLEDGEOPS_ENABLED: "true"
      TJ_AI_KNOWLEDGEOPS_BASE_URL: http://knowledgeops:8080
    depends_on: [knowledgeops]
```

### Evidence Artifacts

| Evidence | How to verify |
|---|---|
| Web retrieval returns results | Check `retrieval.web.latency` metric with `outcome=success` |
| tianji reaches KnowledgeOps | Check tianji logs for `KnowledgeOps platform RAG` debug messages |
| Fallback without KnowledgeOps | Disable `TJ_AI_KNOWLEDGEOPS_ENABLED` → agents use local Advisor |
| Both CIs are green | Open latest GitHub Actions run on `main` for both repos |

## Verification Checklist

- Start the demo stack from a clean checkout.
- Upload or seed a knowledge document.
- Run a RAG answer and confirm citations/evidence are returned.
- Run an Agent workflow and confirm task/step/event state is visible.
- Check Prometheus/Grafana/trace documentation in `docs/observability.md`.
- Open the latest GitHub Actions run and confirm the baseline CI is green.
- *(Cross-repo)* With KnowledgeOps running, verify tianji's KnowledgeAgent reaches it via KnowledgeOpsClient.
- *(Cross-repo)* With KnowledgeOps stopped, verify tianji's KnowledgeAgent falls back to local Advisor.
