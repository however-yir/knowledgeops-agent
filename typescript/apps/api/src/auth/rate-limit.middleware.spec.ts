import { describe, expect, it } from "vitest";
import type { FastifyReply, FastifyRequest } from "fastify";

import { env } from "../config/env.js";
import { isPrivateOrLoopbackAddress, RateLimitMiddleware, resolveClientIp } from "./rate-limit.middleware.js";

interface BucketMap {
  buckets: Map<string, { tokens: number; refreshedAt: number }>;
  evictIdleBuckets(): void;
}

function requestFrom(remoteAddress: string | undefined, forwardedFor?: string | string[]): FastifyRequest {
  return {
    url: "/ai/chat",
    ip: remoteAddress ?? "",
    raw: { socket: remoteAddress === undefined ? undefined : { remoteAddress } },
    headers: forwardedFor === undefined ? {} : { "x-forwarded-for": forwardedFor }
  } as unknown as FastifyRequest;
}

function replyStub(): FastifyReply {
  return { raw: { statusCode: 0, setHeader: () => undefined, end: () => undefined } } as unknown as FastifyReply;
}

describe("resolveClientIp", () => {
  it("uses the direct address when no X-Forwarded-For is present", () => {
    expect(resolveClientIp(requestFrom("203.0.113.7"))).toBe("203.0.113.7");
  });

  it("falls back to the direct address when the socket address is missing", () => {
    expect(resolveClientIp(requestFrom(undefined, "203.0.113.7"))).toBe("unknown");
  });

  it("ignores X-Forwarded-For when the direct peer is a public address", () => {
    expect(resolveClientIp(requestFrom("203.0.113.7", "1.2.3.4, 5.6.7.8"))).toBe("203.0.113.7");
  });

  it("takes the rightmost non-private hop behind a proxy", () => {
    expect(resolveClientIp(requestFrom("127.0.0.1", "203.0.113.9, 10.0.0.1"))).toBe("203.0.113.9");
    expect(resolveClientIp(requestFrom("::1", "10.0.0.1, 198.51.100.4, 10.0.0.2"))).toBe("198.51.100.4");
  });

  it("treats IPv4-mapped IPv6 direct peers as private proxies", () => {
    expect(resolveClientIp(requestFrom("::ffff:127.0.0.1", "203.0.113.9"))).toBe("203.0.113.9");
  });

  it("keeps the direct address when every forwarded hop is private", () => {
    expect(resolveClientIp(requestFrom("127.0.0.1", "10.0.0.1, 192.168.5.5"))).toBe("127.0.0.1");
  });

  it("returns the rightmost hop verbatim for unparseable values (mirrors the Java filter)", () => {
    expect(resolveClientIp(requestFrom("127.0.0.1", "not-an-ip"))).toBe("not-an-ip");
    expect(resolveClientIp(requestFrom("10.0.0.1", ","))).toBe("10.0.0.1");
  });

  it("supports repeated X-Forwarded-For headers", () => {
    expect(resolveClientIp(requestFrom("127.0.0.1", ["10.0.0.1", "203.0.113.9"]))).toBe("203.0.113.9");
  });
});

describe("isPrivateOrLoopbackAddress", () => {
  it("recognizes proxy-side address ranges", () => {
    const privateAddresses = [
      "127.0.0.1", "127.8.8.8", "10.0.0.1", "172.16.0.1", "172.31.255.255",
      "192.168.1.1", "169.254.169.254", "::1", "0:0:0:0:0:0:0:1", "::ffff:10.0.0.1",
      "fe80::1", "fd00::1"
    ];
    const otherAddresses = ["203.0.113.7", "172.32.0.1", "192.169.0.1", "169.255.1.1", "8.8.8.8", "2400:cb00::1", "not-an-ip"];
    for (const address of privateAddresses) expect(isPrivateOrLoopbackAddress(address), address).toBe(true);
    for (const address of otherAddresses) expect(isPrivateOrLoopbackAddress(address), address).toBe(false);
    expect(isPrivateOrLoopbackAddress("")).toBe(false);
  });
});

describe("RateLimitMiddleware bucket hygiene", () => {
  it("evicts fully-refilled idle buckets and keeps active ones", () => {
    const middleware = new RateLimitMiddleware();
    const internals = middleware as unknown as BucketMap;
    const now = Date.now();
    internals.buckets.set("idle", { tokens: env.APP_RATE_LIMIT_CAPACITY, refreshedAt: now - 10 * env.APP_RATE_LIMIT_REFILL_SECONDS * 1000 });
    internals.buckets.set("active", { tokens: 1, refreshedAt: now });

    internals.evictIdleBuckets();

    expect(internals.buckets.has("idle")).toBe(false);
    expect(internals.buckets.has("active")).toBe(true);
  });

  it("clears the bucket map at the hard ceiling instead of growing it", async () => {
    const middleware = new RateLimitMiddleware();
    const internals = middleware as unknown as BucketMap;
    for (let index = 0; index < 50_000; index += 1) {
      internals.buckets.set(`k${index}`, { tokens: 0, refreshedAt: Date.now() });
    }
    let called = false;
    await middleware.use(requestFrom("203.0.113.7"), replyStub(), () => {
      called = true;
    });

    expect(called).toBe(true);
    expect(internals.buckets.size).toBe(1);
  });
});
