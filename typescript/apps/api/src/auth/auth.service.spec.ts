import { describe, expect, it } from "vitest";

import { env } from "../config/env.js";
import { PlatformStore } from "../platform/platform.store.js";
import type { PrismaPersistenceService } from "../platform/prisma.persistence.service.js";
import { AuthService } from "./auth.service.js";

describe("AuthService", () => {
  it("exchanges the local demo API key for JWT credentials", () => {
    const service = new AuthService(new PlatformStore());

    const result = service.exchangeApiKey("local-demo-api-key", "public");

    expect(result.ok).toBe(1);
    expect(result.token).toBeTruthy();
    expect(result.refreshToken).toBeTruthy();
    expect(result.tenantId).toBe("public");
  });

  it("keeps invalid keys distinct from tenant mismatches", () => {
    const service = new AuthService(new PlatformStore());

    expect(service.exchangeApiKey("bad-key", "public")).toEqual({
      ok: 0,
      msg: "invalid api key",
      token: null,
      refreshToken: null,
      tenantId: null,
      expiresInSeconds: null,
      refreshExpiresAt: null,
      refreshWillExpireSoon: null
    });
    expect(service.exchangeApiKey("local-demo-api-key", "other")).toMatchObject({ ok: 0, msg: "tenant mismatch for api key" });
  });

  it("rotates refresh tokens and revokes the consumed token", async () => {
    const service = new AuthService(new PlatformStore());
    const issued = service.exchangeApiKey("local-demo-api-key", "public");

    const refreshed = await service.refresh(issued.refreshToken);

    expect(refreshed.ok).toBe(1);
    expect(refreshed.refreshToken).toBeTruthy();
    await expect(service.refresh(issued.refreshToken)).resolves.toMatchObject({ ok: 0, msg: "invalid refresh token" });
  });

  it("allows only one concurrent refresh consumer", async () => {
    const service = new AuthService(new PlatformStore());
    const issued = service.exchangeApiKey("local-demo-api-key", "public");

    const results = await Promise.all([
      service.refresh(issued.refreshToken),
      service.refresh(issued.refreshToken)
    ]);

    expect(results.filter((result) => result.ok === 1)).toHaveLength(1);
    expect(results.filter((result) => result.ok === 0)).toHaveLength(1);
  });

  it("rejects concurrent replays when a persistence service is injected but Prisma is disabled", async () => {
    const originalPrismaEnabled = env.APP_PRISMA_ENABLED;
    env.APP_PRISMA_ENABLED = false;
    const persistence = { rotateRefreshToken: async () => true } as unknown as PrismaPersistenceService;
    const service = new AuthService(new PlatformStore(), persistence);
    const issued = service.exchangeApiKey("local-demo-api-key", "public");

    try {
      const results = await Promise.all([
        service.refresh(issued.refreshToken),
        service.refresh(issued.refreshToken)
      ]);

      expect(results.filter((result) => result.ok === 1)).toHaveLength(1);
      expect(results.filter((result) => result.ok === 0)).toHaveLength(1);
    } finally {
      env.APP_PRISMA_ENABLED = originalPrismaEnabled;
    }
  });

  it("invalidates the old API key when rotating a named key", () => {
    const service = new AuthService(new PlatformStore());
    const issued = service.issueApiKey("rotate-me", "USER", "public");

    const rotated = service.rotateApiKey("rotate-me", "USER", "public");

    expect(rotated.msg).toBe("rotated");
    expect(service.exchangeApiKey(issued.rawApiKey, "public")).toMatchObject({ ok: 0, msg: "invalid api key" });
    expect(service.exchangeApiKey(rotated.rawApiKey, "public").ok).toBe(1);
  });
});
