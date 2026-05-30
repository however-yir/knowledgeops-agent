import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ServerResponse } from "node:http";

import { newId, nowIso } from "../common/ids.js";
import type { RequestWithContext } from "../common/request-context.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class AuditLogMiddleware implements NestMiddleware {
  constructor(private readonly store: PlatformStore) {}

  use(req: FastifyRequest, res: FastifyReply | ServerResponse, next: () => void): void {
    const started = Date.now();
    const raw = responseRaw(res);
    raw.on("finish", () => {
      const path = req.url.split("?")[0] ?? "/";
      if (path.startsWith("/actuator")) {
        return;
      }
      const request = req as RequestWithContext;
      const tenantHeader = req.headers[TENANT_HEADER] ?? req.headers["x-tenant-id"];
      const tenant = Array.isArray(tenantHeader) ? tenantHeader[0] : tenantHeader;
      this.store.auditLogs.push({
        id: this.store.auditLogs.length + 1,
        requestId: headerValue(req.headers["x-request-id"]) ?? newId("req"),
        traceId: headerValue(req.headers["x-trace-id"]) ?? "",
        tenantId: normalizeTenant(request.context?.tenantId ?? tenant),
        userIdentity: request.context?.identity?.principal ?? "anonymous",
        method: req.method,
        path,
        statusCode: raw.statusCode,
        durationMs: Date.now() - started,
        chatId: extractChatId(req.url),
        jobId: extractQueryParam(req.url, "jobId"),
        extraPayload: safeQuery(req.url),
        createdAt: nowIso()
      });
      this.store.persist();
    });
    next();
  }
}

function responseRaw(res: FastifyReply | ServerResponse): ServerResponse {
  return "raw" in res ? res.raw : res;
}

function headerValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function extractChatId(url: string): string {
  const fromQuery = extractQueryParam(url, "chatId");
  if (fromQuery) {
    return fromQuery;
  }
  const tokens = (url.split("?")[0] ?? "").split("/");
  const uploadIndex = tokens.indexOf("upload");
  return uploadIndex >= 0 ? tokens[uploadIndex + 1] ?? "" : "";
}

function extractQueryParam(url: string, key: string): string {
  return new URL(url, "http://localhost").searchParams.get(key) ?? "";
}

function safeQuery(url: string): string {
  const query = url.split("?")[1] ?? "";
  return query
    .replace(/(api[-_]?key=)[^&]+/gi, "$1***")
    .replace(/(token=)[^&]+/gi, "$1***")
    .replace(/(contact(_info)?=)[^&]+/gi, "$1***")
    .slice(0, 1000);
}
