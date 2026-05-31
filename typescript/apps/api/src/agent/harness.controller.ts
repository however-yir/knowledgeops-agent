import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { readFileSync } from "node:fs";
import { relative, resolve } from "node:path";

import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { env } from "../config/env.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller("ai/harness")
export class HarnessController {
  constructor(private readonly store: PlatformStore, private readonly retrievalService: RetrievalService) {}

  @Get("actions")
  actions() {
    return [
      {
        action: "workspace_read_file",
        runtime: "workspace",
        requiredKeys: ["path"],
        optionalKeys: ["maxBytes"],
        riskLevel: "read",
        trustedOnly: true
      },
      {
        action: "rag_query",
        runtime: "retrieval",
        requiredKeys: ["query"],
        optionalKeys: ["tenantId", "chatId"],
        riskLevel: "read",
        trustedOnly: false
      },
      {
        action: "memory_save",
        runtime: "memory",
        requiredKeys: ["content"],
        optionalKeys: ["tenantId", "userId", "type", "source"],
        riskLevel: "write",
        trustedOnly: true
      },
      {
        action: "graph_search",
        runtime: "graph",
        requiredKeys: ["query"],
        optionalKeys: ["tenantId", "limit"],
        riskLevel: "read",
        trustedOnly: false
      }
    ];
  }

  @Post("actions/preview")
  preview(@Body() request: Record<string, unknown>) {
    const token = newId("ta");
    const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    const decision = evaluatePolicy(request);
    this.store.trustedActions.set(token, { ...request, expiresAt, decision });
    this.store.persist();
    return {
      ok: decision.allowed ? 1 : 0,
      token,
      action: request.action ?? "unknown",
      expiresAt,
      preview: { status: decision.allowed ? "pending_confirmation" : "blocked", request, decision }
    };
  }

  @Post("actions/execute/:token")
  execute(@Param("token") token: string) {
    const started = Date.now();
    const request = this.store.trustedActions.get(token);
    if (!request) {
      return { status: "not_found", source: "trusted-action" };
    }
    this.store.trustedActions.delete(token);
    if (Date.parse(String(request.expiresAt ?? "")) <= Date.now()) {
      return { status: "expired", source: "trusted-action" };
    }
    const decision = evaluatePolicy(request);
    if (!decision.allowed) {
      return this.record(request, "policy", "blocked", Date.now() - started, { error: decision.message });
    }
    try {
      const observation = this.executeAction(request);
      return this.record(request, observation.source, "executed", Date.now() - started, observation);
    } catch (error) {
      return this.record(request, "runtime", "error", Date.now() - started, {
        error: error instanceof Error ? error.message : String(error)
      });
    } finally {
      this.store.persist();
    }
  }

  private executeAction(request: Record<string, unknown>) {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    if (request.action === "rag_query") {
      const query = String(input.query ?? "");
      const tenantId = String(input.tenantId ?? "public");
      const chatId = String(input.chatId ?? "");
      return {
        source: "retrieval",
        action: "rag_query",
        observation: this.retrievalService.answer(query, tenantId, chatId)
      };
    }
    if (request.action === "workspace_read_file") {
      const path = resolveWorkspacePath(String(input.path ?? ""));
      const maxBytes = Math.max(1, Math.min(Number(input.maxBytes ?? 20_000), 200_000));
      return {
        source: "workspace",
        action: "workspace_read_file",
        observation: {
          path: relative(resolve(env.APP_WORKSPACE_ROOT), path),
          content: readFileSync(path, "utf8").slice(0, maxBytes)
        }
      };
    }
    if (request.action === "memory_save") {
      const content = String(input.content ?? "").trim();
      if (!content) {
        throw new Error("content is required");
      }
      const now = nowIso();
      const item = {
        memoryId: newId("mem"),
        tenantId: String(input.tenantId ?? "public"),
        userId: String(input.userId ?? "agent"),
        type: String(input.type ?? "task"),
        content,
        source: String(input.source ?? "agent-harness"),
        confidence: 0.85,
        createdAt: now,
        updatedAt: now
      };
      this.store.memoryItems.push(item);
      return { source: "memory", action: "memory_save", observation: item };
    }
    if (request.action === "graph_search") {
      const query = String(input.query ?? "").toLowerCase();
      const tenantId = String(input.tenantId ?? "public");
      const limit = Math.max(1, Math.min(Number(input.limit ?? 10), 50));
      const entities = this.store.graphEntities
        .filter((entity) => entity.tenantId === tenantId)
        .filter((entity) => `${entity.name} ${entity.description ?? ""} ${entity.aliases.join(" ")}`.toLowerCase().includes(query))
        .slice(0, limit);
      return { source: "graph", action: "graph_search", observation: { entities } };
    }
    return {
      source: "trusted-action",
      action: request.action ?? "unknown",
      observation: { ok: true }
    };
  }

  private record(request: Record<string, unknown>, source: string, status: string, latencyMs: number, observation: unknown) {
    this.store.harnessEvents.push({
      eventId: newId("hevt"),
      action: String(request.action ?? "unknown"),
      source,
      status,
      latencyMs,
      payload: sanitizeObservation(observation),
      createdAt: nowIso()
    });
    return {
      status,
      source,
      action: request.action ?? "unknown",
      observation: sanitizeObservation(observation)
    };
  }
}

function evaluatePolicy(request: Record<string, unknown>): { allowed: boolean; message: string } {
  const action = String(request.action ?? "");
  if (!action) {
    return { allowed: false, message: "action is required" };
  }
  if (action === "workspace_read_file") {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    try {
      resolveWorkspacePath(String(input.path ?? ""));
    } catch (error) {
      return { allowed: false, message: error instanceof Error ? error.message : String(error) };
    }
  }
  return { allowed: true, message: "allowed" };
}

function resolveWorkspacePath(value: string): string {
  if (!value.trim()) {
    throw new Error("path is required");
  }
  const root = resolve(env.APP_WORKSPACE_ROOT);
  const target = resolve(root, value);
  if (target !== root && !target.startsWith(`${root}/`)) {
    throw new Error("path escapes workspace root");
  }
  return target;
}

function sanitizeObservation(value: unknown): unknown {
  const text = JSON.stringify(value)
    .replace(/(api[-_]?key|token|authorization)["']?\s*[:=]\s*["']?[^"',}\s]+/gi, "$1=***")
    .slice(0, 20_000);
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
