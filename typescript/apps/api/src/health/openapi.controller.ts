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
          apiKeyAuth: { type: "apiKey", in: "header", name: "X-API-Key" }
        }
      },
      paths: {
        "/auth/token": postPath("Issue JWT and refresh token"),
        "/auth/refresh": postPath("Refresh JWT"),
        "/auth/api-keys": postPath("Issue API key"),
        "/ai/react/chat": postPath("Run ReAct chat"),
        "/ai/react/chat/stream": postPath("Run streaming ReAct chat"),
        "/ingestion/upload/{chatId}": postPath("Upload knowledge document"),
        "/ai/harness/actions": getPath("List agent harness actions"),
        "/ai/harness/actions/preview": postPath("Preview trusted action"),
        "/ai/harness/actions/execute/{token}": postPath("Execute trusted action"),
        "/ai/evaluation/datasets": getPostPath("List or create evaluation datasets"),
        "/ai/memory/items": getPostPath("List or create memory items"),
        "/ai/graph/entities": getPostPath("List or create graph entities"),
        "/cost/summary": getPath("Read tenant cost summary"),
        "/actuator/health": getPath("Health check"),
        "/actuator/prometheus": getPath("Prometheus metrics")
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
    responses: {
      "200": {
        description: "OK"
      }
    }
  };
}
