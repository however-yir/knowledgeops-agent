import { Body, Controller, Get, Headers, Post, Query } from "@nestjs/common";

import { nowIso } from "../common/ids.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller()
export class OperationsController {
  constructor(private readonly store: PlatformStore) {}

  @Get("cost/summary")
  costSummary(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    const tenantId = normalizeTenant(tenantHeader);
    return {
      tenantId,
      month: new Date().toISOString().slice(0, 7),
      monthlyBudgetUsd: 25,
      hardLimitEnabled: false,
      monthCostUsd: 0,
      monthRequestCount: 0,
      monthInputTokens: 0,
      monthOutputTokens: 0,
      todayCostUsd: 0,
      todayRequestCount: 0,
      budgetRemainingUsd: 25,
      budgetExceeded: false
    };
  }

  @Post("cost/budget")
  updateBudget(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: { tenantId?: string; monthlyBudgetUsd?: number; hardLimitEnabled?: boolean }) {
    const summary = this.costSummary(body.tenantId ?? tenantHeader);
    return {
      ...summary,
      monthlyBudgetUsd: body.monthlyBudgetUsd ?? summary.monthlyBudgetUsd,
      hardLimitEnabled: body.hardLimitEnabled ?? summary.hardLimitEnabled
    };
  }

  @Get("audit/logs")
  auditLogs(@Query("limit") limit = "50", @Query("tenantId") tenantId?: string) {
    const bounded = Math.max(1, Math.min(Number(limit), 200));
    const logs = this.store.auditLogs.filter((log) => !tenantId || log.tenantId === tenantId).slice(-bounded);
    return logs.length > 0 ? logs : [{
      id: 1,
      tenantId: tenantId ?? "public",
      method: "GET",
      path: "/audit/logs",
      statusCode: 200,
      durationMs: 0,
      createdAt: nowIso()
    }];
  }

  @Get("ai/memory/items")
  memory(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    return this.store.memoryItems.filter((item) => item.tenantId === normalizeTenant(tenantHeader));
  }

  @Post("ai/memory/items")
  addMemory(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: Record<string, unknown>) {
    const item = { tenantId: normalizeTenant(tenantHeader), ...body, createdAt: nowIso() };
    this.store.memoryItems.push(item);
    return item;
  }

  @Get("ai/graph/entities")
  graphEntities(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    return this.store.graphEntities.filter((entity) => entity.tenantId === normalizeTenant(tenantHeader));
  }

  @Post("ai/graph/entities")
  addGraphEntity(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: Record<string, unknown>) {
    const entity = { tenantId: normalizeTenant(tenantHeader), ...body, createdAt: nowIso() };
    this.store.graphEntities.push(entity);
    return entity;
  }
}
