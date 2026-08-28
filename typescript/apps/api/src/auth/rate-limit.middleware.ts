import { Injectable, NestMiddleware, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import { Redis } from "ioredis";
import type { IncomingMessage, ServerResponse } from "node:http";

import type { RequestWithContext } from "../common/request-context.js";
import { normalizeTenant } from "../common/tenant.js";
import { traceIdFrom } from "../common/trace.js";
import { env } from "../config/env.js";

interface Bucket {
  tokens: number;
  refreshedAt: number;
}

// Hard ceiling on the per-process bucket map so a burst of distinct keys
// cannot exhaust the heap. Once exceeded we drop everything; legitimate
// callers rebuild their bucket on the next request.
const MAX_BUCKETS = 50_000;

@Injectable()
export class RateLimitMiddleware implements NestMiddleware, OnModuleInit, OnModuleDestroy {
  private readonly buckets = new Map<string, Bucket>();
  private redis: Redis | undefined;
  private evictionTimer: NodeJS.Timeout | undefined;

  onModuleInit(): void {
    if (!env.APP_RATE_LIMIT_ENABLED) return;
    this.evictionTimer = setInterval(() => this.evictIdleBuckets(), env.APP_RATE_LIMIT_EVICT_INTERVAL_MS);
    this.evictionTimer.unref?.();
  }

  onModuleDestroy(): void {
    clearInterval(this.evictionTimer);
  }

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
    if (this.buckets.size >= MAX_BUCKETS) {
      this.buckets.clear();
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

  // Drops buckets that fully refilled (idle for at least the refill window) so
  // the per-tenant/per-IP bucket map does not grow without bound. Evicted keys
  // simply start with a fresh bucket on their next request.
  private evictIdleBuckets(): void {
    if (!env.APP_RATE_LIMIT_ENABLED || this.buckets.size === 0) return;
    for (const [key, bucket] of this.buckets) {
      if (this.refill(bucket).tokens >= env.APP_RATE_LIMIT_CAPACITY) {
        this.buckets.delete(key);
      }
    }
  }

  private resolveKey(req: RequestWithContext): string {
    const tenant = normalizeTenant(req.context?.tenantId);
    const principal = req.context?.identity?.principal;
    return principal ? `tenant:${tenant}:principal:${principal}` : `tenant:${tenant}:ip:${resolveClientIp(req)}`;
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

/**
 * Pick the most useful client IP for the rate-limit key. When the request
 * comes through a reverse proxy, the direct socket address is the proxy's
 * own address, so every anonymous caller would share one bucket and a
 * single attacker could exhaust the limit for the whole tenant. Parse
 * X-Forwarded-For only when the direct peer is a private/loopback address
 * (i.e. we are behind a proxy), and prefer the rightmost non-private hop so
 * a malicious caller cannot inject a fake leftmost entry to rotate their
 * own bucket. Unparseable values fail closed to the direct address.
 *
 * Nest registers middlewares on Fastify through middie, so `req` arrives as
 * the raw IncomingMessage (with `socket`, no `raw` wrapper); guards see the
 * FastifyRequest (with `raw`). Read the socket address from both shapes.
 */
export function resolveClientIp(req: Pick<FastifyRequest, "ip" | "raw" | "headers">): string {
  const carrier = req as unknown as (IncomingMessage & { raw?: IncomingMessage }) & { ip?: string };
  const direct = normalizeAddress(carrier.raw?.socket?.remoteAddress ?? carrier.socket?.remoteAddress)
    ?? (carrier.ip?.trim() ? carrier.ip.trim() : "unknown");
  const header = req.headers["x-forwarded-for"];
  const forwarded = (Array.isArray(header) ? header.join(",") : header ?? "").trim();
  if (!forwarded) return direct;
  if (!isPrivateOrLoopbackAddress(direct)) return direct;
  for (const hop of forwarded.split(",").reverse()) {
    const candidate = hop.trim();
    if (candidate && !isPrivateOrLoopbackAddress(candidate)) return candidate;
  }
  return direct;
}

/**
 * Textual classification of addresses a reverse proxy would connect from:
 * IPv4 loopback/RFC1918/link-local and IPv6 loopback/link-local/ULA. Parse
 * failures are treated as not-private so the direct address keeps being used.
 */
export function isPrivateOrLoopbackAddress(raw: string): boolean {
  const address = normalizeAddress(raw);
  if (!address) return false;
  if (address === "::1" || address === "0:0:0:0:0:0:0:1") return true;
  if (address.startsWith("127.") || address.startsWith("10.") || address.startsWith("192.168.") || address.startsWith("169.254.")) {
    return true;
  }
  if (address.startsWith("172.")) {
    const second = Number(address.split(".")[1] ?? Number.NaN);
    return second >= 16 && second <= 31;
  }
  if (address.includes(":")) {
    return /^fe[89ab]/.test(address) || /^f[cd]/.test(address);
  }
  return false;
}

function normalizeAddress(raw: string | null | undefined): string | undefined {
  const trimmed = raw?.trim().toLowerCase();
  if (!trimmed) return undefined;
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/.exec(trimmed);
  return mapped ? mapped[1] : trimmed;
}
