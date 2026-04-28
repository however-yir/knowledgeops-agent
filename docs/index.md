# KnowledgeOps Agent Documentation

KnowledgeOps Agent is an enterprise-ready Spring AI platform for intelligent Q&A, retrieval-augmented generation, controlled tool execution, asynchronous ingestion, security governance, and production operations.

## Start Here

- [Project README](https://github.com/however-yir/knowledgeops-agent#readme)
- [Enterprise Architecture](architecture-enterprise.md)
- [Enterprise Deployment Guide](deployment-enterprise.md)
- [Operations Manual](operations.md)
- [Roadmap](roadmap.md)
- [Distributed and Observability Drill](drills/distributed-and-observability-drill.md)
- [Runbook Template](drills/runbook_template.md)

## Platform Capabilities

| Area | Coverage |
|---|---|
| AI workflows | Chat, PDF RAG, ReAct trace, tool calling, conversation history |
| Ingestion | Redis Stream or RabbitMQ queues, retries, DLQ, idempotency, status tracking |
| Security | API Key, JWT, refresh tokens, RBAC, tenant isolation, rate limiting, audit logs |
| Operations | Docker Compose, Flyway, Prometheus, Loki, Tempo, Alertmanager, structured logs |
| Quality | CI, unit tests, integration tests, regression evaluation, k6 load tests |

## Quick Links

- Swagger UI: `/swagger-ui/index.html`
- Health: `/actuator/health`
- Metrics: `/actuator/prometheus`
- Frontend console: `http://localhost:8088`
