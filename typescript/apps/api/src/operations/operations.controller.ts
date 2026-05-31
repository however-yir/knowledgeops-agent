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

  @Get("ai/memory/context")
  memoryContext(
    @Headers(TENANT_HEADER) tenantHeader: string | undefined,
    @Query("userId") userId = "anonymous",
    @Query("prompt") prompt = "",
    @Query("limit") limit = "8"
  ) {
    const tenantId = normalizeTenant(tenantHeader);
    const now = Date.now();
    const tokens = prompt.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const items = this.store.memoryItems
      .filter((item) => item.tenantId === tenantId && item.userId === userId)
      .filter((item) => !item.expiresAt || Date.parse(item.expiresAt) > now)
      .map((item) => ({
        ...item,
        relevance: clamp(tokens.filter((token) => item.content.toLowerCase().includes(token)).length / Math.max(1, tokens.length) + item.confidence * 0.2, 0, 1)
      }))
      .sort((a, b) => b.relevance - a.relevance || b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, Math.max(1, Math.min(Number(limit), 50)));
    return {
      userId,
      tenantId,
      items,
      snapshot: items.map((item) => `[${item.type}:${item.confidence}] ${item.content}`).join("\n")
    };
  }

  @Post("ai/memory/cleanup")
  cleanupMemory(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    const tenantId = normalizeTenant(tenantHeader);
    const before = this.store.memoryItems.length;
    const now = Date.now();
    for (let index = this.store.memoryItems.length - 1; index >= 0; index -= 1) {
      const item = this.store.memoryItems[index];
      if (item.tenantId === tenantId && item.expiresAt && Date.parse(item.expiresAt) <= now) {
        this.store.memoryItems.splice(index, 1);
        appendMemoryEvent(this.store, item.memoryId, "EXPIRE", "retention cleanup");
      }
    }
    this.store.persist();
    return { ok: 1, removed: before - this.store.memoryItems.length };
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

  @Get("ai/graph/entities/:entityId/neighbors")
  graphNeighbors(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Param("entityId") entityId: string, @Query("limit") limit = "50") {
    const tenantId = normalizeTenant(tenantHeader);
    const max = Math.max(1, Math.min(Number(limit), 100));
    const relations = this.store.graphRelations
      .filter((relation) => relation.tenantId === tenantId && (relation.sourceEntityId === entityId || relation.targetEntityId === entityId))
      .sort((a, b) => b.weight - a.weight)
      .slice(0, max);
    const entityIds = new Set(relations.flatMap((relation) => [relation.sourceEntityId, relation.targetEntityId]));
    const entities = this.store.graphEntities.filter((entity) => entity.tenantId === tenantId && entityIds.has(entity.entityId));
    return { entityId, relations, entities };
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

  @Get("ai/graph/facts")
  graphFacts(
    @Headers(TENANT_HEADER) tenantHeader: string | undefined,
    @Query("q") query = "",
    @Query("predicate") predicate?: string,
    @Query("minConfidence") minConfidence = "0",
    @Query("limit") limit = "50"
  ) {
    const tenantId = normalizeTenant(tenantHeader);
    const normalized = query.trim().toLowerCase();
    const min = clamp(Number(minConfidence), 0, 1);
    return this.store.graphFacts
      .filter((fact) => fact.tenantId === tenantId)
      .filter((fact) => !predicate || fact.predicate === predicate)
      .filter((fact) => fact.confidence >= min)
      .filter((fact) => !normalized || `${fact.subject} ${fact.predicate} ${fact.object}`.toLowerCase().includes(normalized))
      .sort((a, b) => b.confidence - a.confidence || b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, Math.max(1, Math.min(Number(limit), 100)));
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
