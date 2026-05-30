import { describe, expect, it } from "vitest";
import type { ExecutionContext } from "@nestjs/common";

import { env } from "../config/env.js";
import { PlatformStore } from "../platform/platform.store.js";
import { AuthGuard } from "./auth.guard.js";
import { AuthService } from "./auth.service.js";

describe("AuthGuard", () => {
  it("enforces Java-compatible route permissions when security is enabled", () => {
    const previous = env.APP_SECURITY_ENABLED;
    env.APP_SECURITY_ENABLED = true;
    try {
      const guard = new AuthGuard(new AuthService(new PlatformStore()));

      expect(guard.canActivate(contextFor("GET", "/cost/summary", "local-demo-api-key"))).toBe(true);
      expect(() => guard.canActivate(contextFor("POST", "/cost/budget", "bad-key"))).toThrow("authentication required");
      expect(() => guard.canActivate(contextFor("POST", "/cost/budget", "local-demo-api-key", "other"))).toThrow("authentication required");
    } finally {
      env.APP_SECURITY_ENABLED = previous;
    }
  });
});

function contextFor(method: string, url: string, apiKey: string, tenantId = "public"): ExecutionContext {
  return {
    switchToHttp: () => ({
      getRequest: () => ({
        method,
        url,
        headers: {
          "x-api-key": apiKey,
          "x-tenant-id": tenantId
        }
      })
    })
  } as ExecutionContext;
}
