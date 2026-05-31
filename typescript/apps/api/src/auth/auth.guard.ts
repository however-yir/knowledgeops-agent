import { CanActivate, ExecutionContext, ForbiddenException, Injectable, UnauthorizedException } from "@nestjs/common";
import type { FastifyRequest } from "fastify";

import type { RequestWithContext } from "../common/request-context.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { env } from "../config/env.js";
import { AuthService } from "./auth.service.js";

const PUBLIC_ROUTES = [
  { method: "GET", path: "/actuator/health" },
  { method: "GET", path: "/" },
  { method: "POST", path: "/auth/token" },
  { method: "POST", path: "/auth/refresh" }
];

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(private readonly authService: AuthService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<FastifyRequest>() as RequestWithContext;
    request.context = request.context ?? this.resolveContext(request);
    if (!env.APP_SECURITY_ENABLED) {
      return true;
    }
    if (isPublic(request)) {
      return true;
    }
    const identity = request.context?.identity;
    if (identity && hasRoutePermission(request, identity.permissions)) {
      return true;
    }
    if (identity) {
      throw new ForbiddenException("insufficient permission");
    }
    throw new UnauthorizedException("authentication required");
  }

  private resolveContext(request: FastifyRequest) {
    const tenantHeader = request.headers[TENANT_HEADER] ?? request.headers["x-tenant-id"];
    const headerTenant = Array.isArray(tenantHeader) ? tenantHeader[0] : tenantHeader;
    const authorization = request.headers.authorization;
    const apiKey = request.headers["x-api-key"];
    const rawApiKey = Array.isArray(apiKey) ? apiKey[0] : apiKey;
    const rawBearer = authorization?.startsWith("Bearer ") ? authorization.slice("Bearer ".length) : undefined;
    const identity = rawBearer
      ? this.authService.parseJwt(rawBearer)
      : rawApiKey
        ? this.authService.authenticateApiKey(rawApiKey, typeof headerTenant === "string" ? headerTenant : undefined)
        : undefined;
    return {
      tenantId: normalizeTenant(identity?.tenantId ?? headerTenant),
      identity
    };
  }
}

function isPublic(request: FastifyRequest): boolean {
  const method = request.method.toUpperCase();
  const path = request.url.split("?")[0] ?? "/";
  return PUBLIC_ROUTES.some((route) => route.method === method && route.path === path)
    || path.startsWith("/v3/api-docs")
    || path.startsWith("/swagger-ui")
    || path === "/swagger-ui.html"
    || path === "/error";
}

function hasRoutePermission(request: FastifyRequest, permissions: string[]): boolean {
  const method = request.method.toUpperCase();
  const path = request.url.split("?")[0] ?? "/";
  const allowed = new Set(permissions);
  const required = requiredAuthorities(method, path);
  return required.length === 0 || required.some((authority) => allowed.has(authority));
}

function requiredAuthorities(method: string, path: string): string[] {
  if (path === "/actuator/prometheus") {
    return ["PERM_METRICS_READ", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "GET" && path === "/audit/logs") {
    return ["PERM_AUDIT_READ", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "POST" && path.startsWith("/auth/api-keys")) {
    return ["PERM_AUTH_KEY_MANAGE", "ROLE_ADMIN"];
  }
  if (method === "GET" && (path === "/ai/chat" || path === "/ai/service")) {
    return ["PERM_CHAT_READ", "PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if (method === "POST" && (path === "/ai/chat" || path === "/ai/service")) {
    return ["PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if (method === "POST" && (path === "/ai/react/chat" || path === "/ai/react/chat/stream")) {
    return ["PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if ((method === "GET" || method === "POST") && path.startsWith("/ai/harness/")) {
    return ["PERM_AGENT_TRUSTED", "ROLE_ADMIN"];
  }
  if (method === "GET" && path.startsWith("/ai/evaluation/")) {
    return ["PERM_EVAL_READ", "PERM_EVAL_WRITE", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "POST" && path.startsWith("/ai/evaluation/")) {
    return ["PERM_EVAL_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && path.startsWith("/ai/sessions")) {
    return ["PERM_SESSION_READ", "PERM_CHAT_READ", "PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if ((method === "PUT" || method === "POST") && path.startsWith("/ai/sessions")) {
    return ["PERM_SESSION_WRITE", "PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if (method === "POST" && path === "/ai/feedback") {
    return ["PERM_FEEDBACK_WRITE", "PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && (path === "/ai/pdf/chat" || path.startsWith("/ai/pdf/file/"))) {
    return ["PERM_RAG_READ", "ROLE_ADMIN"];
  }
  if (method === "POST" && (path.startsWith("/ai/pdf/upload/") || path.startsWith("/ingestion/upload/"))) {
    return ["PERM_INGESTION_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && path === "/cost/summary") {
    return ["PERM_COST_READ", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "POST" && path === "/cost/budget") {
    return ["PERM_COST_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && path.startsWith("/ai/memory/")) {
    return ["PERM_SESSION_READ", "PERM_CHAT_READ", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if ((method === "POST" || method === "DELETE") && path.startsWith("/ai/memory/")) {
    return ["PERM_SESSION_WRITE", "PERM_CHAT_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && path.startsWith("/ai/graph/")) {
    return ["PERM_RAG_READ", "PERM_CHAT_READ", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "POST" && path.startsWith("/ai/graph/")) {
    return ["PERM_INGESTION_WRITE", "ROLE_ADMIN"];
  }
  if (method === "GET" && (path === "/ingestion/jobs" || path.startsWith("/ingestion/jobs/"))) {
    return ["PERM_INGESTION_READ", "PERM_INGESTION_WRITE", "ROLE_ADMIN", "ROLE_OPS"];
  }
  if (method === "POST" && path === "/ingestion/jobs/process") {
    return ["ROLE_ADMIN"];
  }
  if (path.startsWith("/ingestion/") || path.startsWith("/ai/pdf/")) {
    return ["PERM_INGESTION_WRITE", "ROLE_ADMIN"];
  }
  return [];
}
