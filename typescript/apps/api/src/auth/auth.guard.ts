import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
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
    if (request.context?.identity) {
      return true;
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
  return PUBLIC_ROUTES.some((route) => route.method === method && route.path === path);
}
