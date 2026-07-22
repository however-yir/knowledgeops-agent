import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import { mergeMap, type Observable } from "rxjs";

import { PlatformStore } from "../platform/platform.store.js";
import { traceIdFrom } from "./trace.js";

interface EnvelopeLike {
  ok?: unknown;
  msg?: unknown;
  data?: unknown;
  code?: unknown;
  traceId?: unknown;
}

@Injectable()
export class ApiResponseInterceptor implements NestInterceptor {
  constructor(private readonly store: PlatformStore) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<FastifyRequest>();
    const response = context.switchToHttp().getResponse<{ header?: (name: string, value: string) => unknown }>();
    const traceId = traceIdFrom(request);
    response.header?.("X-Trace-ID", traceId);
    return next.handle().pipe(mergeMap(async (value) => {
      await this.store.waitForPersistence();
      return shouldBypassEnvelope(request) ? value : envelope(value, traceId);
    }));
  }
}

function shouldBypassEnvelope(request: FastifyRequest): boolean {
  const path = request.url.split("?")[0] ?? "/";
  return path === "/actuator/prometheus"
    || path === "/metrics"
    || path.startsWith("/v3/api-docs")
    || path.startsWith("/swagger-ui")
    || path === "/swagger-ui.html"
    || path.startsWith("/ai/pdf/file/")
    || path.endsWith("/stream");
}

function envelope(value: unknown, traceId: string): unknown {
  if (!isRecord(value)) {
    return { ok: 1, msg: "ok", data: value };
  }
  const candidate = value as EnvelopeLike;
  if (candidate.ok === 0) {
    return {
      ok: 0,
      msg: typeof candidate.msg === "string" ? candidate.msg : "error",
      code: typeof candidate.code === "string" ? candidate.code : "BUSINESS_ERROR",
      traceId: typeof candidate.traceId === "string" ? candidate.traceId : traceId
    };
  }
  if (candidate.ok === 1 && "data" in candidate) {
    return {
      ok: 1,
      msg: typeof candidate.msg === "string" ? candidate.msg : "ok",
      data: candidate.data
    };
  }
  if (candidate.ok === 1) {
    const { ok: _ok, msg, ...data } = value as Record<string, unknown>;
    return {
      ok: 1,
      msg: typeof msg === "string" ? msg : "ok",
      data
    };
  }
  return { ok: 1, msg: "ok", data: value };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
