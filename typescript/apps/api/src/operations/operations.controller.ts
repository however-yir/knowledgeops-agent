import { Body, Controller, Delete, Get, Header, Headers, Param, Post, Query } from "@nestjs/common";

import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";

@Controller()
export class OperationsController {
  constructor(
    private readonly store: PlatformStore,
    private readonly costService: TenantCostService,
    private readonly metrics: MetricsService
  ) {}

  @Get("cost/summary")
  costSummary(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    return this.costService.summary(tenantHeader);
  }

  @Post("cost/budget")
  updateBudget(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: { tenantId?: string; monthlyBudgetUsd?: number; hardLimitEnabled?: boolean }) {
    const payload = body ?? {};
    return this.costService.updateBudget({ ...payload, tenantId: payload.tenantId ?? tenantHeader });
  }

  @Get("audit/logs")
  auditLogs(@Query("limit") limit = "50", @Query("tenantId") tenantId?: string) {
    const bounded = Math.max(1, Math.min(Number(limit), 200));
    return this.store.auditLogs
      .filter((log) => !tenantId || log.tenantId === tenantId)
      .slice(-bounded)
      .reverse();
  }

  @Get("actuator/prometheus")
  @Header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
  prometheus() {
    return this.metrics.prometheus();
  }

  @Get("ai/memory/items")
  memory(
    @Headers(TENANT_HEADER) tenantHeader: string | undefined,
    @Query("userId") userId = "anonymous",
    @Query("type") type?: string,
    @Query("limit") limit = "20"
  ) {
    const tenantId = normalizeTenant(tenantHeader);
    const now = Date.now();
    return this.store.memoryItems
      .filter((item) => item.tenantId === tenantId && item.userId === userId)
      .filter((item) => !type || item.type === type)
      .filter((item) => !item.expiresAt || Date.parse(item.expiresAt) > now)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, Math.max(1, Math.min(Number(limit), 100)));
  }

  @Post("ai/memory/items")
  addMemory(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: {
    userId?: string;
    type?: string;
    content?: string;
    source?: string;
    sourceTaskId?: string;
    confidence?: number;
    expiresAt?: string;
  }) {
    if (!body.content?.trim()) {
      return { ok: 0, msg: "memory content is required" };
    }
    const now = nowIso();
    const item = {
      memoryId: newId("mem"),
      tenantId: normalizeTenant(tenantHeader),
      userId: body.userId?.trim() || "anonymous",
      type: body.type?.trim() || "long",
      content: body.content.trim(),
      source: body.source,
      sourceTaskId: body.sourceTaskId,
      confidence: clamp(body.confidence ?? 0.85, 0, 1),
      expiresAt: body.expiresAt,
      createdAt: now,
      updatedAt: now
    };
    this.store.memoryItems.push(item);
    appendMemoryEvent(this.store, item.memoryId, "CREATE", `saved ${item.type} memory`);
    this.store.persist();
    return item;
  }

  @Delete("ai/memory/items/:memoryId")
  deleteMemory(@Param("memoryId") memoryId: string) {
    const index = this.store.memoryItems.findIndex((item) => item.memoryId === memoryId);
    if (index < 0) {
      return { ok: 0, msg: "memory not found" };
    }
    this.store.memoryItems.splice(index, 1);
    appendMemoryEvent(this.store, memoryId, "DELETE", "manual deletion");
    this.store.persist();
    return { ok: 1, msg: "deleted" };
  }

  @Get("ai/memory/items/:memoryId/events")
  memoryEvents(@Param("memoryId") memoryId: string) {
    return this.store.memoryEvents.get(memoryId) ?? [];
  }

  @Get("ai/graph/entities")
  graphEntities(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Query("q") query = "", @Query("type") type?: string, @Query("limit") limit = "50") {
    const tenantId = normalizeTenant(tenantHeader);
    const normalized = query.trim().toLowerCase();
    return this.store.graphEntities
      .filter((entity) => entity.tenantId === tenantId)
      .filter((entity) => !type || entity.type === type)
      .filter((entity) => !normalized || `${entity.name} ${entity.description ?? ""} ${entity.aliases.join(" ")}`.toLowerCase().includes(normalized))
      .slice(0, Math.max(1, Math.min(Number(limit), 100)));
  }

  @Post("ai/graph/entities")
  addGraphEntity(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: {
    name?: string;
    type?: string;
    description?: string;
    aliases?: string[];
    metadata?: Record<string, unknown>;
  }) {
    if (!body.name?.trim()) {
      return { ok: 0, msg: "entity name is required" };
    }
    const now = nowIso();
    const entity = {
      entityId: newId("kgent"),
      tenantId: normalizeTenant(tenantHeader),
      name: body.name.trim(),
      type: body.type?.trim() || "UNKNOWN",
      description: body.description,
      aliases: body.aliases ?? [],
      metadata: body.metadata ?? {},
      createdAt: now,
      updatedAt: now
    };
    this.store.graphEntities.push(entity);
    this.store.persist();
    return entity;
  }

  @Post("ai/graph/relations")
  addGraphRelation(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: {
    sourceEntityId?: string;
    targetEntityId?: string;
    relationType?: string;
    weight?: number;
    metadata?: Record<string, unknown>;
  }) {
    if (!body.sourceEntityId || !body.targetEntityId) {
      return { ok: 0, msg: "sourceEntityId and targetEntityId are required" };
    }
    const now = nowIso();
    const relation = {
      relationId: newId("kgrel"),
      tenantId: normalizeTenant(tenantHeader),
      sourceEntityId: body.sourceEntityId,
      targetEntityId: body.targetEntityId,
      relationType: body.relationType || "RELATED_TO",
      weight: clamp(body.weight ?? 1, 0, 1),
      metadata: body.metadata ?? {},
      createdAt: now,
      updatedAt: now
    };
    this.store.graphRelations.push(relation);
    this.store.persist();
    return relation;
  }

  @Post("ai/graph/facts")
  addGraphFact(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: {
    subject?: string;
    predicate?: string;
    object?: string;
    confidence?: number;
    source?: string;
    metadata?: Record<string, unknown>;
  }) {
    if (!body.subject?.trim() || !body.predicate?.trim() || !body.object?.trim()) {
      return { ok: 0, msg: "subject, predicate and object are required" };
    }
    const now = nowIso();
    const fact = {
      factId: newId("kgfact"),
      tenantId: normalizeTenant(tenantHeader),
      subject: body.subject.trim(),
      predicate: body.predicate.trim(),
      object: body.object.trim(),
      confidence: clamp(body.confidence ?? 0.7, 0, 1),
      source: body.source,
      metadata: body.metadata ?? {},
      createdAt: now,
      updatedAt: now
    };
    this.store.graphFacts.push(fact);
    this.store.persist();
    return fact;
  }
}

function appendMemoryEvent(store: PlatformStore, memoryId: string, action: string, reason: string): void {
  const events = store.memoryEvents.get(memoryId) ?? [];
  events.push({
    eventId: newId("mevt"),
    memoryId,
    action,
    reason,
    createdAt: nowIso()
  });
  store.memoryEvents.set(memoryId, events);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
