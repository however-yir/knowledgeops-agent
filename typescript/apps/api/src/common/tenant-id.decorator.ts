import { createParamDecorator, type ExecutionContext } from "@nestjs/common";
import type { FastifyRequest } from "fastify";

import { tenantIdFromRequest } from "./request-context.js";

export const TenantId = createParamDecorator((_data: unknown, context: ExecutionContext): string => {
  return tenantIdFromRequest(context.switchToHttp().getRequest<FastifyRequest>());
});
