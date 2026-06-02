import { Controller, Get, Header } from "@nestjs/common";

@Controller()
export class OpenApiController {
  @Get("v3/api-docs")
  apiDocs() {
    return {
      openapi: "3.0.3",
      info: {
        title: "Intelligent Q&A Knowledge Platform API",
        version: "v1"
      },
      security: [{ bearerAuth: [] }, { apiKeyAuth: [] }],
      components: {
        securitySchemes: {
          bearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
          apiKeyAuth: { type: "apiKey", in: "header", name: "X-API-Key" },
          tenantHeader: { type: "apiKey", in: "header", name: "X-Tenant-ID" }
        }
      },
      paths: {
        "/auth/token": postPath("Issue JWT and refresh token"),
        "/auth/refresh": postPath("Refresh JWT"),
        "/auth/api-keys": postPath("Issue API key"),
        "/ai/chat": postPath("Run standard chat"),
        "/ai/chat/stream": postPath("Stream standard chat"),
        "/ai/react/chat": postPath("Run ReAct chat"),
        "/ai/react/chat/stream": postPath("Run streaming ReAct chat"),
        "/ai/pdf/chat": postPath("Run RAG chat"),
        "/ai/pdf/upload/{chatId}": postPath("Upload PDF knowledge document"),
        "/ingestion/upload/{chatId}": postPath("Upload knowledge document"),
        "/ingestion/jobs": getPath("List ingestion jobs"),
        "/ingestion/jobs/{jobId}": getPath("Read ingestion job"),
        "/ai/sessions": getPath("List sessions"),
        "/ai/sessions/{sessionId}": getPath("Read session"),
        "/ai/feedback": postPath("Submit chat feedback"),
        "/ai/harness/actions": getPath("List agent harness actions"),
        "/ai/harness/actions/preview": postPath("Preview trusted action"),
        "/ai/harness/actions/execute/{token}": postPath("Execute trusted action"),
        "/ai/evaluation/datasets": getPostPath("List or create evaluation datasets"),
        "/ai/evaluation/runs": postPath("Run an evaluation dataset"),
        "/audit/logs": getPath("Read audit logs"),
        "/ai/memory/items": getPostPath("List or create memory items"),
        "/ai/graph/entities": getPostPath("List or create graph entities"),
        "/cost/summary": getPath("Read tenant cost summary"),
        "/cost/budget": postPath("Update tenant budget"),
        "/actuator/health": getPath("Health check"),
        "/health": getPath("Health check alias"),
        "/actuator/prometheus": getPath("Prometheus metrics"),
        "/metrics": getPath("Prometheus metrics alias")
      }
    };
  }

  @Get("swagger-ui")
  @Get("swagger-ui.html")
  @Get("swagger-ui/index.html")
  @Header("Content-Type", "text/html; charset=utf-8")
  swaggerUi() {
    return "<!doctype html><title>KnowledgeOps API</title><body><a href=\"/v3/api-docs\">OpenAPI JSON</a></body>";
  }
}

function getPath(summary: string) {
  return { get: operation(summary) };
}

function postPath(summary: string) {
  return { post: operation(summary) };
}

function getPostPath(summary: string) {
  return { get: operation(summary), post: operation(summary) };
}

function operation(summary: string) {
  return {
    summary,
    parameters: [
      { name: "Authorization", in: "header", required: false, schema: { type: "string" } },
      { name: "X-API-Key", in: "header", required: false, schema: { type: "string" } },
      { name: "X-Tenant-ID", in: "header", required: false, schema: { type: "string" } }
    ],
    responses: {
      "200": {
        description: "OK"
      }
    }
  };
}
