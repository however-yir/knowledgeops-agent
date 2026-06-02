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

  it("keeps cost summaries tenant-scoped", () => {
    const service = new TenantCostService(new PlatformStore());

    service.recordUsage("public", "low", 100, 0);
    service.recordUsage("acme", "high", 100, 0);

    expect(service.summary("public").monthRequestCount).toBe(1);
    expect(service.summary("acme").monthRequestCount).toBe(1);
    expect(service.summary("public").monthCostUsd).not.toBe(service.summary("acme").monthCostUsd);
  });

  it("rejects negative budget updates", () => {
    const service = new TenantCostService(new PlatformStore());

    expect(() => service.updateBudget({ tenantId: "public", monthlyBudgetUsd: -1 })).toThrow("monthlyBudgetUsd must be non-negative");
  });
});
