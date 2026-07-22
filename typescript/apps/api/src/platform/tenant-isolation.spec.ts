import { describe, expect, it } from "vitest";
import type { SessionState } from "@knowledgeops/shared";

import type { AiService } from "../ai/ai.service.js";
import { EvaluationController } from "../evaluation/evaluation.controller.js";
import { OperationsController } from "../operations/operations.controller.js";
import { SessionsService } from "../sessions/sessions.service.js";
import { RetrievalService } from "../ai/retrieval.service.js";
import { WorkflowService } from "../workflow/workflow.service.js";
import { MetricsService } from "./metrics.service.js";
import { PlatformStore } from "./platform.store.js";
import { TenantCostService } from "./tenant-cost.service.js";

describe("tenant isolation", () => {
  it("keeps identical session IDs isolated per tenant", () => {
    const service = new SessionsService(new PlatformStore());

    service.upsert("tenant-a", "shared", session("A"));
    service.upsert("tenant-b", "shared", session("B"));

    expect(service.get("tenant-a", "shared").title).toBe("A");
    expect(service.get("tenant-b", "shared").title).toBe("B");
    expect(service.list("tenant-a", 1, 20, false).items).toHaveLength(1);
    expect(() => service.get("tenant-c", "shared")).toThrow("session not found");
  });

  it("hides workflow tasks from other tenants", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const task = service.createTask("tenant-a", "DEEP_RESEARCH", "secret topic");

    expect(service.getTask("tenant-a", task.taskId)?.taskId).toBe(task.taskId);
    expect(service.getTask("tenant-b", task.taskId)).toBeUndefined();
    expect(service.getEvents("tenant-b", task.taskId)).toEqual([]);
  });

  it("prevents cross-tenant evaluation reads and baseline writes", async () => {
    const store = new PlatformStore();
    const controller = new EvaluationController(store, fakeAiService());
    const dataset = controller.createDataset("tenant-a", {
      name: "private",
      cases: [{ question: "q" }]
    });
    if (!("datasetId" in dataset)) {
      throw new Error("expected dataset");
    }
    const run = await controller.triggerRun("tenant-a", dataset.datasetId);
    if (!("runId" in run)) {
      throw new Error("expected run");
    }

    expect(controller.getRun("tenant-b", run.runId)).toMatchObject({ ok: 0, msg: "run not found" });
    expect(controller.compare("tenant-b", dataset.datasetId)).toMatchObject({ ok: 0, msg: "dataset not found" });
    expect(controller.baseline("tenant-b", run.runId)).toMatchObject({ ok: 0, msg: "run not found" });
    expect(store.evalDatasets.get(dataset.datasetId)?.baselineRunId).toBeUndefined();
  });

  it("scopes audit, budgets, and memory mutations to the authenticated tenant", () => {
    const store = new PlatformStore();
    const cost = new TenantCostService(store);
    const controller = new OperationsController(store, cost, new MetricsService(store));
    store.auditLogs.push(
      { tenantId: "tenant-a", method: "GET", path: "/a", statusCode: 200, createdAt: "2026-01-01" },
      { tenantId: "tenant-b", method: "GET", path: "/b", statusCode: 200, createdAt: "2026-01-02" }
    );
    const memory = controller.addMemory("tenant-a", { content: "secret" });
    if (!("memoryId" in memory)) {
      throw new Error("expected memory");
    }

    controller.updateBudget("tenant-a", { tenantId: "tenant-b", monthlyBudgetUsd: 99 });

    expect(controller.auditLogs("tenant-a")).toHaveLength(1);
    expect(controller.auditLogs("tenant-a")[0]?.path).toBe("/a");
    expect(cost.summary("tenant-a").monthlyBudgetUsd).toBe(99);
    expect(cost.summary("tenant-b").monthlyBudgetUsd).not.toBe(99);
    expect(controller.deleteMemory("tenant-b", memory.memoryId)).toMatchObject({ ok: 0, msg: "memory not found" });
    expect(controller.deleteMemory("tenant-a", memory.memoryId)).toMatchObject({ ok: 1 });
  });
});

function session(title: string): SessionState {
  return {
    id: "ignored",
    title,
    updatedAt: Date.now(),
    modelProfile: "balanced",
    streaming: false,
    pinned: false,
    archived: false,
    workspaceId: "default",
    activeBranchId: "main",
    branches: [{
      id: "main",
      title: "Main",
      parentBranchId: null,
      parentMessageId: null,
      updatedAt: Date.now(),
      messages: [],
      traceSteps: []
    }]
  };
}

function fakeAiService(): AiService {
  return {
    reactChat: async () => ({
      ok: 1,
      msg: "ok",
      chatId: "eval",
      answer: "answer",
      model: "test",
      usage: { inputTokens: 1, outputTokens: 1, totalTokens: 2 },
      traceId: "trace",
      citations: [],
      evidence: ["evidence"],
      trace: []
    })
  } as unknown as AiService;
}
