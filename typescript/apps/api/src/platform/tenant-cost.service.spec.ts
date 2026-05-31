import { describe, expect, it } from "vitest";

import { PlatformStore } from "./platform.store.js";
import { TenantCostService } from "./tenant-cost.service.js";

describe("TenantCostService", () => {
  it("records tenant usage and enforces hard budgets", () => {
    const store = new PlatformStore();
    const service = new TenantCostService(store);

    service.updateBudget({ tenantId: "acme", monthlyBudgetUsd: 0.000001, hardLimitEnabled: true });
    service.recordUsage("acme", "high", 100, 100);

    const summary = service.summary("acme");
    expect(summary.monthRequestCount).toBe(1);
    expect(summary.monthInputTokens).toBe(100);
    expect(() => service.assertBudget("acme", "high", 10_000, 10_000)).toThrow("tenant budget exceeded");
  });
});
