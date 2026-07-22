import type { ExecutionContext } from "@nestjs/common";
import { firstValueFrom, of } from "rxjs";
import { describe, expect, it, vi } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
import { ApiResponseInterceptor } from "./api-response.interceptor.js";

describe("ApiResponseInterceptor", () => {
  it("preserves Java response bodies after persistence completes", async () => {
    let release: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    const store = {
      waitForPersistence: vi.fn(() => pending)
    } as unknown as PlatformStore;
    const header = vi.fn();
    const context = {
      switchToHttp: () => ({
        getRequest: () => ({ url: "/cost/summary", headers: {} }),
        getResponse: () => ({ header })
      })
    } as ExecutionContext;
    const value = { tenantId: "public", monthRequestCount: 1 };
    const result = firstValueFrom(new ApiResponseInterceptor(store).intercept(context, {
      handle: () => of(value)
    }));
    let settled = false;
    void result.then(() => {
      settled = true;
    });

    await Promise.resolve();
    expect(settled).toBe(false);
    release?.();

    await expect(result).resolves.toBe(value);
    expect(store.waitForPersistence).toHaveBeenCalledOnce();
    expect(header).toHaveBeenCalledWith("X-Trace-ID", expect.any(String));
  });
});
