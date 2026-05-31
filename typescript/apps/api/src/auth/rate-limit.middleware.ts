import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ServerResponse } from "node:http";

import type { RequestWithContext } from "../common/request-context.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";

interface Bucket {
  tokens: number;
  refreshedAt: number;
}

@Injectable()
export class RateLimitMiddleware implements NestMiddleware {
  private readonly buckets = new Map<string, Bucket>();

  use(req: FastifyRequest, res: FastifyReply | ServerResponse, next: () => void): void {
    if (!env.APP_RATE_LIMIT_ENABLED || req.url.startsWith("/actuator")) {
      next();
      return;
    }
    const key = this.resolveKey(req as RequestWithContext);
    const bucket = this.refill(this.buckets.get(key) ?? { tokens: env.APP_RATE_LIMIT_CAPACITY, refreshedAt: Date.now() });
    if (bucket.tokens < 1) {
      const raw = responseRaw(res);
      raw.statusCode = 429;
      raw.setHeader("Content-Type", "application/json");
      raw.end(JSON.stringify({ ok: 0, msg: "rate limit exceeded" }));
      return;
    }
    bucket.tokens -= 1;
    this.buckets.set(key, bucket);
    next();
  }

  private refill(bucket: Bucket): Bucket {
    const now = Date.now();
    const elapsedWindows = Math.floor((now - bucket.refreshedAt) / (env.APP_RATE_LIMIT_REFILL_SECONDS * 1000));
    if (elapsedWindows <= 0) {
      return bucket;
    }
    return {
      tokens: Math.min(env.APP_RATE_LIMIT_CAPACITY, bucket.tokens + elapsedWindows * env.APP_RATE_LIMIT_CAPACITY),
      refreshedAt: bucket.refreshedAt + elapsedWindows * env.APP_RATE_LIMIT_REFILL_SECONDS * 1000
    };
  }

  private resolveKey(req: RequestWithContext): string {
    const tenant = normalizeTenant(req.context?.tenantId);
    const principal = req.context?.identity?.principal;
    return principal ? `tenant:${tenant}:principal:${principal}` : `tenant:${tenant}:ip:${req.ip ?? "unknown"}`;
  }
}

function responseRaw(res: FastifyReply | ServerResponse): ServerResponse {
  return "raw" in res ? res.raw : res;
}
