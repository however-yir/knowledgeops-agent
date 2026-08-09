# AI Engineering Project Matrix

This repository is one part of a five-project AI engineering portfolio. The matrix is meant to make each project's role clear without repeating the full table in every README front page.

| Repo | Role | Core scenario | Engineering proof |
|---|---|---|---|
| [knowledgeops-agent](https://github.com/however-yir/knowledgeops-agent) | Enterprise Spring AI RAG platform | Governed enterprise knowledge Q&A | Spring AI, RAG, JWT/RBAC, async ingestion, observability, regression evaluation |
| [tianji-ai-agent](https://github.com/however-yir/tianji-ai-agent) | Business Agent engineering case | Course consulting, recommendation, and pre-order flow | Java, Spring AI, multi-agent routing, Tool Calling, MCP, SSE, multimodal entry points |
| [nebula-kb](https://github.com/however-yir/nebula-kb) | Local AI Knowledge Platform | Knowledge lifecycle + RAG engine (DeepDoc) + AI chat (Open WebUI) | Django, PostgreSQL, Redis, RAGFlow, Open WebUI, lifecycle workflow |
| [forgepilot-studio](https://github.com/however-yir/forgepilot-studio) | AI engineering execution workspace | Auditable AI coding task execution for teams | Python, FastAPI, React, runtime sandbox, MCP governance, audit replay |
| [however-microservices-lab](https://github.com/however-yir/however-microservices-lab) | Cloud-native microservices and AI lab | Multi-language microservices with AI assistant integration | Go, Python, Java, Node.js, C#, Kubernetes, gRPC, Ollama/Gemini |

## How This Repository Fits

`knowledgeops-agent` is the enterprise backend slice. It proves that RAG can be treated as a governed platform with tenant boundaries, asynchronous ingestion, auditability, observability, and repeatable quality checks.

## Cross-Repo Verification

The relationship between KnowledgeOps and tianji is verified by:

1. **Code path**: `KnowledgeOpsClient` in tianji calls implemented KnowledgeOps Agent REST APIs such as `/ai/rag/search` and `/ai/graph/search`; memory enrichment remains a planned integration because MemoryService is not yet exposed as REST.
2. **Fallback strategy**: When platform is unavailable, tianji agents fall back to local VectorStore + Advisor
3. **CI evidence**: Both repositories have green CI on `main` branch
4. **Docker compose**: See `docs/evidence/README.md` for a 2-service + 3-env-var cross-repo Docker Compose
