import type { FastifyRequest } from "fastify";

import { newId } from "./ids.js";

export function traceIdFrom(request: FastifyRequest): string {
  const existing = headerValue(request.headers["x-trace-id"]) ?? headerValue(request.headers["x-request-id"]);
  if (existing?.trim()) {
    return existing.trim();
  }
  const mutable = request as FastifyRequest & { traceId?: string };
  mutable.traceId ??= newId("trace");
  return mutable.traceId;
}

function headerValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
