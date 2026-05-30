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
});
