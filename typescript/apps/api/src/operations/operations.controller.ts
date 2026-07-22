import { Body, Controller, Delete, Get, Header, Param, Post, Query } from "@nestjs/common";

import { newId, nowIso } from "../common/ids.js";
import { TenantId } from "../common/tenant-id.decorator.js";
import { normalizeTenant } from "../common/tenant.js";
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
  costSummary(@TenantId() tenantId: string) {
    return this.costService.summary(tenantId);
  }

  @Post("cost/budget")
  updateBudget(
    @TenantId() tenantId: string,
    @Body() body: { tenantId?: string; monthlyBudgetUsd?: number; hardLimitEnabled?: boolean }
  ) {
    return this.costService.updateBudget({ ...(body ?? {}), tenantId });
  }

  @Get("audit/logs")
  auditLogs(@TenantId() tenantId: string, @Query("limit") limit = "50") {
    const tenant = normalizeTenant(tenantId);
    const bounded = Math.max(1, Math.min(Number(limit), 200));
    return this.store.auditLogs
      .filter((log) => log.tenantId === tenant)
      .slice(-bounded)
      .reverse()
      .map((log) => ({
        tenantId: String(log.tenantId ?? "public"),
        principal: String(log.principal ?? log.userIdentity ?? "anonymous"),
        method: String(log.method ?? ""),
        path: String(log.path ?? ""),
        status: Number(log.status ?? log.statusCode ?? 0),
        createdAt: String(log.createdAt ?? "")
      }));
  }

  @Get(["actuator/prometheus", "metrics"])
  @Header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
  prometheus() {
    return this.metrics.prometheus();
  }

  @Get("ai/memory/items")
  memory(
    @TenantId() tenantId: string,
    @Query("userId") userId = "anonymous",
    @Query("type") type?: string,
    @Query("limit") limit = "20"
  ) {
    const tenant = normalizeTenant(tenantId);
    const now = Date.now();
    return this.store.memoryItems
      .filter((item) => item.tenantId === tenant && item.userId === userId)
      .filter((item) => !type || item.type === type)
      .filter((item) => !item.expiresAt || Date.parse(item.expiresAt) > now)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, Math.max(1, Math.min(Number(limit), 100)));
  }

  @Post("ai/memory/items")
  addMemory(@TenantId() tenantId: string, @Body() body: {
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
      tenantId: normalizeTenant(tenantId),
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
  deleteMemory(@TenantId() tenantId: string, @Param("memoryId") memoryId: string) {
    const tenant = normalizeTenant(tenantId);
    const index = this.store.memoryItems.findIndex((item) => item.tenantId === tenant && item.memoryId === memoryId);
    if (index < 0) {
      return { ok: 0, msg: "memory not found" };
    }
    this.store.memoryItems.splice(index, 1);
    this.store.markMemoryDeleted(memoryId);
    appendMemoryEvent(this.store, memoryId, "DELETE", "manual deletion");
    this.store.persist();
    return { ok: 1, msg: "deleted" };
  }

  @Get("ai/memory/items/:memoryId/events")
  memoryEvents(@TenantId() tenantId: string, @Param("memoryId") memoryId: string) {
    const tenant = normalizeTenant(tenantId);
    const owned = this.store.memoryItems.some((item) => item.tenantId === tenant && item.memoryId === memoryId);
    return owned ? this.store.memoryEvents.get(memoryId) ?? [] : [];
  }

  @Get("ai/memory/context")
  memoryContext(
    @TenantId() tenantId: string,
    @Query("userId") userId = "anonymous",
    @Query("prompt") prompt = "",
    @Query("limit") limit = "8"
  ) {
    const tenant = normalizeTenant(tenantId);
    const now = Date.now();
    const tokens = prompt.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const items = this.store.memoryItems
      .filter((item) => item.tenantId === tenant && item.userId === userId)
      .filter((item) => !item.expiresAt || Date.parse(item.expiresAt) > now)
      .map((item) => ({
        ...item,
        relevance: clamp(
          tokens.filter((token) => item.content.toLowerCase().includes(token)).length / Math.max(1, tokens.length)
            + item.confidence * 0.2,
          0,
          1
        )
      }))
      .sort((a, b) => b.relevance - a.relevance || b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, Math.max(1, Math.min(Number(limit), 50)));
    return {
      userId,
      tenantId: tenant,
      items,
      snapshot: items.map((item) => `[${item.type}:${item.confidence}] ${item.content}`).join("\n")
    };
  }

  @Post("ai/memory/cleanup")
  cleanupMemory(@TenantId() tenantId: string) {
    const tenant = normalizeTenant(tenantId);
    const before = this.store.memoryItems.length;
    const now = Date.now();
    for (let index = this.store.memoryItems.length - 1; index >= 0; index -= 1) {
      const item = this.store.memoryItems[index];
      if (item.tenantId === tenant && item.expiresAt && Date.parse(item.expiresAt) <= now) {
        this.store.memoryItems.splice(index, 1);
        this.store.markMemoryDeleted(item.memoryId);
        appendMemoryEvent(this.store, item.memoryId, "EXPIRE", "retention cleanup");
      }
    }
    this.store.persist();
    return { ok: 1, removed: before - this.store.memoryItems.length };
  }

  @Get("ai/graph/entities")
  graphEntities(
    @TenantId() tenantId: string,
    @Query("q") query = "",
    @Query("type") type?: string,
    @Query("limit") limit = "50"
  ) {
    const tenant = normalizeTenant(tenantId);
    const normalized = query.trim().toLowerCase();
    return this.store.graphEntities
      .filter((entity) => entity.tenantId === tenant)
      .filter((entity) => !type || entity.type === type)
      .filter((entity) => !normalized || `${entity.name} ${entity.description ?? ""} ${entity.aliases.join(" ")}`.toLowerCase().includes(normalized))
      .slice(0, Math.max(1, Math.min(Number(limit), 100)));
  }

  @Post("ai/graph/entities")
  addGraphEntity(@TenantId() tenantId: string, @Body() body: {
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
      tenantId: normalizeTenant(tenantId),
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
  addGraphRelation(@TenantId() tenantId: string, @Body() body: {
    sourceEntityId?: string;
    targetEntityId?: string;
    relationType?: string;
    weight?: number;
    metadata?: Record<string, unknown>;
  }) {
    const tenant = normalizeTenant(tenantId);
    if (!body.sourceEntityId || !body.targetEntityId) {
      return { ok: 0, msg: "sourceEntityId and targetEntityId are required" };
    }
    const sourceOwned = this.store.graphEntities.some((item) => item.tenantId === tenant && item.entityId === body.sourceEntityId);
    const targetOwned = this.store.graphEntities.some((item) => item.tenantId === tenant && item.entityId === body.targetEntityId);
    if (!sourceOwned || !targetOwned) {
      return { ok: 0, msg: "graph entity not found" };
    }
    const now = nowIso();
    const relation = {
      relationId: newId("kgrel"),
      tenantId: tenant,
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
  graphNeighbors(@TenantId() tenantId: string, @Param("entityId") entityId: string, @Query("limit") limit = "50") {
    const tenant = normalizeTenant(tenantId);
    const owned = this.store.graphEntities.some((entity) => entity.tenantId === tenant && entity.entityId === entityId);
    if (!owned) {
      return { entityId, relations: [], entities: [] };
    }
    const max = Math.max(1, Math.min(Number(limit), 100));
    const relations = this.store.graphRelations
      .filter((relation) => relation.tenantId === tenant && (relation.sourceEntityId === entityId || relation.targetEntityId === entityId))
      .sort((a, b) => b.weight - a.weight)
      .slice(0, max);
    const entityIds = new Set(relations.flatMap((relation) => [relation.sourceEntityId, relation.targetEntityId]));
    const entities = this.store.graphEntities.filter((entity) => entity.tenantId === tenant && entityIds.has(entity.entityId));
    return { entityId, relations, entities };
  }

  @Post("ai/graph/facts")
  addGraphFact(@TenantId() tenantId: string, @Body() body: {
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
      tenantId: normalizeTenant(tenantId),
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
    @TenantId() tenantId: string,
    @Query("q") query = "",
    @Query("predicate") predicate?: string,
    @Query("minConfidence") minConfidence = "0",
    @Query("limit") limit = "50"
  ) {
    const tenant = normalizeTenant(tenantId);
    const normalized = query.trim().toLowerCase();
    const min = clamp(Number(minConfidence), 0, 1);
    return this.store.graphFacts
      .filter((fact) => fact.tenantId === tenant)
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
