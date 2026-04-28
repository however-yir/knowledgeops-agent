# Roadmap

This roadmap tracks release-oriented improvements for KnowledgeOps Agent. Items may change as the project receives usage feedback and operational evidence.

## v1.1.0 Focus

The v1.1.0 cycle is focused on making the platform easier to deploy, observe, and extend in production-like environments.

| Area | Item | Outcome |
|---|---|---|
| Security | OIDC/SAML SSO integration design | Enterprise identity integration path is documented and ready for implementation |
| Retrieval | Pluggable reranker interface | Teams can compare rerankers without rewriting the RAG pipeline |
| Observability | Grafana dashboard bundle | Operators get ready-made dashboards for API latency, ingestion, retrieval, and errors |
| Deployment | Helm chart and Kubernetes guide | Users can move from Docker Compose to Kubernetes with clear defaults |
| Agents | MCP tool bridge exploration | External tools can be connected through a standard agent-tool integration path |

## Backlog

- Automated alert remediation scripts.
- Larger multi-hop and hallucination evaluation sets.
- Deployment evidence reports with screenshots and capacity notes.
- More frontend console workflows for ingestion, audit, and cost governance.
