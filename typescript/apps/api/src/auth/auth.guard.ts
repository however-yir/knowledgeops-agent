import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import type { FastifyRequest } from "fastify";

import type { RequestWithContext } from "../common/request-context.js";
import { env } from "../config/env.js";

const PUBLIC_ROUTES = [
  { method: "GET", path: "/actuator/health" },
  { method: "GET", path: "/" },
  { method: "POST", path: "/auth/token" },
  { method: "POST", path: "/auth/refresh" }
];

@Injectable()
export class AuthGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    if (!env.APP_SECURITY_ENABLED) {
      return true;
    }
    const request = context.switchToHttp().getRequest<FastifyRequest>() as RequestWithContext;
    if (isPublic(request)) {
      return true;
    }
    if (request.context?.identity) {
      return true;
    }
    throw new UnauthorizedException("authentication required");
  }
}

function isPublic(request: FastifyRequest): boolean {
  const method = request.method.toUpperCase();
  const path = request.url.split("?")[0] ?? "/";
  return PUBLIC_ROUTES.some((route) => route.method === method && route.path === path);
}
