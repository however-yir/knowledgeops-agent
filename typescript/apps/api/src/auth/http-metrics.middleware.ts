import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ServerResponse } from "node:http";

import { MetricsService } from "../platform/metrics.service.js";

@Injectable()
export class HttpMetricsMiddleware implements NestMiddleware {
  constructor(private readonly metrics: MetricsService) {}

  use(req: FastifyRequest, res: FastifyReply | ServerResponse, next: () => void): void {
    const started = Date.now();
    const raw = "raw" in res ? res.raw : res;
    raw.on("finish", () => {
      const path = normalizePath(req.url.split("?")[0] ?? "/");
      const latencyMs = Date.now() - started;
      this.metrics.increment("http_requests_total", { method: req.method, path, status: raw.statusCode });
      this.metrics.increment("http_requests_latency_ms_sum", { method: req.method, path }, latencyMs);
      this.metrics.observe("http_request_duration_ms", latencyMs, { method: req.method, path, status: raw.statusCode });
    });
    next();
  }
}

function normalizePath(path: string): string {
  if (path.startsWith("/actuator")) {
    return "/actuator";
  }
  if (path.startsWith("/ai/pdf/file/")) {
    return "/ai/pdf/file/{chatId}";
  }
  if (path.startsWith("/ingestion/jobs/")) {
    return "/ingestion/jobs/{jobId}";
  }
  return path;
}
