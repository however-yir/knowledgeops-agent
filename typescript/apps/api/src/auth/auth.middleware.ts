import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";

import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import type { RequestWithContext } from "../common/request-context.js";
import { AuthService } from "./auth.service.js";

@Injectable()
export class AuthContextMiddleware implements NestMiddleware {
  constructor(private readonly authService: AuthService) {}

  use(req: FastifyRequest, _res: FastifyReply, next: () => void): void {
    const request = req as RequestWithContext;
    const tenantHeader = req.headers[TENANT_HEADER] ?? req.headers["x-tenant-id"];
    const headerTenant = Array.isArray(tenantHeader) ? tenantHeader[0] : tenantHeader;
    const authorization = req.headers.authorization;
    const apiKey = req.headers["x-api-key"];
    const rawApiKey = Array.isArray(apiKey) ? apiKey[0] : apiKey;
    const rawBearer = authorization?.startsWith("Bearer ") ? authorization.slice("Bearer ".length) : undefined;
    const identity = rawBearer
      ? this.authService.parseJwt(rawBearer)
      : rawApiKey
        ? this.authService.authenticateApiKey(rawApiKey)
        : undefined;
    const normalizedHeaderTenant = typeof headerTenant === "string" ? normalizeTenant(headerTenant) : undefined;
    request.context = {
      tenantId: normalizeTenant(identity?.tenantId ?? normalizedHeaderTenant),
      identity,
      authenticationError: identity && normalizedHeaderTenant && normalizedHeaderTenant !== identity.tenantId
        ? "tenant header does not match authenticated tenant"
        : undefined
    };
    next();
  }
}
