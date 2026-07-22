import type { FastifyRequest } from "fastify";

import type { AuthIdentity } from "../platform/platform.store.js";

export interface RequestContext {
  tenantId: string;
  identity?: AuthIdentity;
  authenticationError?: string;
}

export type RequestWithContext = FastifyRequest & {
  context?: RequestContext;
};

export function tenantIdFromRequest(request?: FastifyRequest): string {
  return request ? (request as RequestWithContext).context?.tenantId ?? "public" : "public";
}
