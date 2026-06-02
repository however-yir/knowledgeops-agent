import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import { Redis } from "ioredis";
import type { ServerResponse } from "node:http";

import type { RequestWithContext } from "../common/request-context.js";
import { normalizeTenant } from "../common/tenant.js";
import { traceIdFrom } from "../common/trace.js";
import { env } from "../config/env.js";

interface Bucket {
  tokens: number;
  refreshedAt: number;
}

@Injectable()
export class RateLimitMiddleware implements NestMiddleware {
  private readonly buckets = new Map<string, Bucket>();
  private redis: Redis | undefined;

  async use(req: FastifyRequest, res: FastifyReply | ServerResponse, next: () => void): Promise<void> {
    if (!env.APP_RATE_LIMIT_ENABLED || req.url.startsWith("/actuator")) {
      next();
      return;
    }
    const key = this.resolveKey(req as RequestWithContext);
    if (env.APP_DISTRIBUTED_RATE_LIMIT_ENABLED) {
      const allowed = await this.distributedAllowed(key).catch(() => true);
      if (!allowed) {
        reject(req, res);
        return;
      }
      next();
      return;
    }
    const bucket = this.refill(this.buckets.get(key) ?? { tokens: env.APP_RATE_LIMIT_CAPACITY, refreshedAt: Date.now() });
    if (bucket.tokens < 1) {
      reject(req, res);
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

  private async distributedAllowed(key: string): Promise<boolean> {
    this.redis ??= new Redis(env.APP_REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 1 });
    const windowKey = `rate:${key}:${Math.floor(Date.now() / (env.APP_RATE_LIMIT_REFILL_SECONDS * 1000))}`;
    const count = await this.redis.incr(windowKey);
    if (count === 1) {
      await this.redis.expire(windowKey, env.APP_RATE_LIMIT_REFILL_SECONDS + 5);
    }
    return count <= env.APP_RATE_LIMIT_CAPACITY;
  }
}

function responseRaw(res: FastifyReply | ServerResponse): ServerResponse {
  return "raw" in res ? res.raw : res;
}

function reject(req: FastifyRequest, res: FastifyReply | ServerResponse): void {
  const traceId = traceIdFrom(req);
  const raw = responseRaw(res);
  raw.statusCode = 429;
  raw.setHeader("Content-Type", "application/json");
  raw.setHeader("X-Trace-ID", traceId);
  raw.end(JSON.stringify({ ok: 0, msg: "rate limit exceeded", code: "RATE_LIMIT_EXCEEDED", traceId }));
}
