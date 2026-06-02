import { describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
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

    expect(service.exchangeApiKey("bad-key", "public")).toMatchObject({ ok: 0, msg: "invalid api key" });
    expect(service.exchangeApiKey("local-demo-api-key", "other")).toMatchObject({ ok: 0, msg: "tenant mismatch for api key" });
  });

  it("rotates refresh tokens and revokes the consumed token", () => {
    const service = new AuthService(new PlatformStore());
    const issued = service.exchangeApiKey("local-demo-api-key", "public");

    const refreshed = service.refresh(issued.refreshToken);

    expect(refreshed.ok).toBe(1);
    expect(refreshed.refreshToken).toBeTruthy();
    expect(service.refresh(issued.refreshToken)).toMatchObject({ ok: 0, msg: "invalid refresh token" });
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
