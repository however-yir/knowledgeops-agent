import type { FastifyRequest } from "fastify";

import type { AuthIdentity } from "../platform/platform.store.js";

export interface RequestContext {
  tenantId: string;
  identity?: AuthIdentity;
}

export type RequestWithContext = FastifyRequest & {
  context?: RequestContext;
};
