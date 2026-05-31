import { Injectable } from "@nestjs/common";

import { nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { PlatformStore, tenantUsageKey } from "./platform.store.js";

export interface TenantCostSummary {
  tenantId: string;
  month: string;
  monthlyBudgetUsd: number;
  hardLimitEnabled: boolean;
  monthCostUsd: number;
  monthRequestCount: number;
  monthInputTokens: number;
  monthOutputTokens: number;
  todayCostUsd: number;
  todayRequestCount: number;
  budgetRemainingUsd: number;
  budgetExceeded: boolean;
}

@Injectable()
export class TenantCostService {
  constructor(private readonly store: PlatformStore) {}

  assertBudget(tenantId: string | undefined, costTier: string | undefined, inputTokens: number, outputTokens: number): void {
    if (!env.APP_COST_ENABLED) {
      return;
    }
    const tenant = normalizeTenant(tenantId);
    const budget = this.ensureBudget(tenant);
    const projected = this.monthCost(tenant, currentMonth()) + this.calculateCost(costTier, inputTokens + outputTokens);
    if (budget.hardLimitEnabled && projected > budget.monthlyBudgetUsd) {
      throw new Error("tenant budget exceeded, request blocked");
    }
  }

  recordUsage(tenantId: string | undefined, costTier: string | undefined, inputTokens: number, outputTokens: number): void {
    if (!env.APP_COST_ENABLED) {
      return;
    }
    const tenant = normalizeTenant(tenantId);
    this.ensureBudget(tenant);
    const today = new Date().toISOString().slice(0, 10);
    const key = tenantUsageKey(tenant, today);
    const existing = this.store.tenantUsageDaily.get(key);
    const now = nowIso();
    const usage = existing ?? {
      tenantId: tenant,
      usageDate: today,
      requestCount: 0,
      inputTokens: 0,
      outputTokens: 0,
      totalCostUsd: 0,
      createdAt: now,
      updatedAt: now
    };
    usage.requestCount += 1;
    usage.inputTokens += Math.max(0, inputTokens);
    usage.outputTokens += Math.max(0, outputTokens);
    usage.totalCostUsd = roundMoney(usage.totalCostUsd + this.calculateCost(costTier, inputTokens + outputTokens), 6);
    usage.updatedAt = now;
    this.store.tenantUsageDaily.set(key, usage);
    this.store.persist();
  }

  summary(tenantId: string | undefined): TenantCostSummary {
    const tenant = normalizeTenant(tenantId);
    const budget = this.ensureBudget(tenant);
    const month = currentMonth();
    const today = new Date().toISOString().slice(0, 10);
    const monthRows = [...this.store.tenantUsageDaily.values()]
      .filter((usage) => usage.tenantId === tenant && usage.usageDate.startsWith(month));
    const todayRows = monthRows.filter((usage) => usage.usageDate === today);
    const monthCostUsd = roundMoney(sum(monthRows.map((usage) => usage.totalCostUsd)), 4);
    const todayCostUsd = roundMoney(sum(todayRows.map((usage) => usage.totalCostUsd)), 4);
    const budgetRemainingUsd = roundMoney(Math.max(0, budget.monthlyBudgetUsd - monthCostUsd), 4);
    return {
      tenantId: tenant,
      month,
      monthlyBudgetUsd: budget.monthlyBudgetUsd,
      hardLimitEnabled: budget.hardLimitEnabled,
      monthCostUsd,
      monthRequestCount: sum(monthRows.map((usage) => usage.requestCount)),
      monthInputTokens: sum(monthRows.map((usage) => usage.inputTokens)),
      monthOutputTokens: sum(monthRows.map((usage) => usage.outputTokens)),
      todayCostUsd,
      todayRequestCount: sum(todayRows.map((usage) => usage.requestCount)),
      budgetRemainingUsd,
      budgetExceeded: monthCostUsd > budget.monthlyBudgetUsd
    };
  }

  updateBudget(request: { tenantId?: string; monthlyBudgetUsd?: number; hardLimitEnabled?: boolean }): TenantCostSummary {
    const tenant = normalizeTenant(request.tenantId);
    const existing = this.ensureBudget(tenant);
    if (request.monthlyBudgetUsd !== undefined && request.monthlyBudgetUsd < 0) {
      throw new Error("monthlyBudgetUsd must be non-negative");
    }
    this.store.tenantBudgets.set(tenant, {
      tenantId: tenant,
      monthlyBudgetUsd: request.monthlyBudgetUsd ?? existing.monthlyBudgetUsd,
      hardLimitEnabled: request.hardLimitEnabled ?? existing.hardLimitEnabled,
      createdAt: existing.createdAt,
      updatedAt: nowIso()
    });
    this.store.persist();
    return this.summary(tenant);
  }

  estimateTokens(text: string | undefined): number {
    if (!text?.trim()) {
      return 0;
    }
    const length = [...text].length;
    return Math.max(1, Math.ceil(length / env.APP_COST_TOKEN_ESTIMATE_DIVISOR));
  }

  calculateCost(costTier: string | undefined, totalTokens: number): number {
    const tier = (costTier ?? "balanced").toLowerCase();
    const unit = tier === "high" || tier === "quality"
      ? env.APP_COST_USD_PER_1K_HIGH
      : tier === "low" || tier === "economy"
        ? env.APP_COST_USD_PER_1K_LOW
        : env.APP_COST_USD_PER_1K_BALANCED;
    return roundMoney(Math.max(0, totalTokens) * unit / 1000, 6);
  }

  private ensureBudget(tenantId: string) {
    const existing = this.store.tenantBudgets.get(tenantId);
    if (existing) {
      return existing;
    }
    const now = nowIso();
    const budget = {
      tenantId,
      monthlyBudgetUsd: env.APP_COST_DEFAULT_MONTHLY_BUDGET_USD,
      hardLimitEnabled: env.APP_COST_DEFAULT_HARD_LIMIT_ENABLED,
      createdAt: now,
      updatedAt: now
    };
    this.store.tenantBudgets.set(tenantId, budget);
    this.store.persist();
    return budget;
  }

  private monthCost(tenantId: string, month: string): number {
    return sum([...this.store.tenantUsageDaily.values()]
      .filter((usage) => usage.tenantId === tenantId && usage.usageDate.startsWith(month))
      .map((usage) => usage.totalCostUsd));
  }
}

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7);
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function roundMoney(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
