import { describe, expect, it } from "vitest";
import type { SessionState } from "@knowledgeops/shared";

import { RetrievalService } from "../ai/retrieval.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { SessionsService } from "../sessions/sessions.service.js";
import { WorkflowService } from "./workflow.service.js";

describe("WorkflowService", () => {
  it("runs deep research through the Java task, step, and event lifecycle", () => {
    const store = new PlatformStore();
    const retrieval = new RetrievalService(store);
    const service = new WorkflowService(store, retrieval, new MetricsService(store));

    const task = service.executeResearch("public", "Heat safety");
    const detail = service.getTask("public", task.taskId);

    expect(task.status).toBe("DONE");
    expect(task.finalOutput).toContain("## 1. 执行摘要");
    expect(task.finalOutput).toContain("## 2. 关键发现");
    expect(task.finalOutput).toContain("## 3. 详细分析");
    expect(task.finalOutput).toContain("## 4. 结论与建议");
    expect(detail?.steps.map((step) => step.agentName)).toEqual([
      "ResearchPlanner", "RagResearchAgent", "RagResearchAgent", "RagResearchAgent", "ReportWriter"
    ]);
    expect(detail?.steps.every((step) => step.status === "COMPLETED")).toBe(true);
    expect(detail?.steps[0]?.observation).toMatchObject({
      subQuestions: expect.arrayContaining([expect.stringContaining("Heat safety")]),
      strategy: "breadth_first"
    });
    expect(detail?.events[0]).toMatchObject({
      eventType: "STATE_CHANGED",
      payload: { from: "CREATED", to: "PLANNING" }
    });
    expect(detail?.events.at(-1)).toMatchObject({ eventType: "TASK_COMPLETED", payload: { status: "DONE" } });
  });

  it("lists workflow tasks only for the requested tenant without detail events", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));

    const publicTask = service.createTask("public", "DEEP_RESEARCH", "public topic");
    service.createTask("acme", "DEEP_RESEARCH", "acme topic");

    expect(publicTask.status).toBe("PLANNING");
    expect(service.listTasks("public", 1, 20)).toHaveLength(1);
    expect(service.listTasks("public", 1, 20)[0]).toMatchObject({ tenantId: "public", events: [] });
    expect(service.listTasks("acme", 1, 20)[0]?.tenantId).toBe("acme");
    expect(service.getTask("acme", publicTask.taskId)).toBeUndefined();
    expect(service.getEvents("acme", publicTask.taskId)).toEqual([]);
  });

  it("processes one queued research task at a time", async () => {
    const store = new PlatformStore();
    const retrieval = new RetrievalService(store);
    const service = new WorkflowService(store, retrieval, new MetricsService(store));
    const task = service.enqueueResearch("public", "queued heat safety");

    const processed = await service.processQueuedTasks();

    expect(processed).toBe(1);
    expect(service.getTask("public", task.taskId)?.status).toBe("DONE");
    expect(service.getTask("public", task.taskId)?.events.some((event) => event.eventType === "TASK_COMPLETED")).toBe(true);
  });

  it("attaches the tenant-scoped workflow snapshot to a session message", () => {
    const store = new PlatformStore();
    const sessions = new SessionsService(store);
    sessions.upsert("tenant-a", "session-1", session());
    const service = new WorkflowService(
      store,
      new RetrievalService(store),
      new MetricsService(store),
      undefined,
      undefined,
      sessions
    );
    const task = service.startReactTask("tenant-a", "question", "", "chat-1", "session-1");
    service.completeReactTask("tenant-a", task.taskId, "answer");

    service.attachSessionSnapshot("tenant-b", task.taskId, "foreign-trace", "session-1", "main", "answer-1");
    expect(sessions.get("tenant-a", "session-1").branches[0]?.messages[0]).not.toHaveProperty("taskId");

    service.attachSessionSnapshot("tenant-a", task.taskId, "trace-1", "session-1", "main", "answer-1");

    expect(sessions.get("tenant-a", "session-1").branches[0]?.messages[0]).toMatchObject({
      id: "answer-1",
      taskId: task.taskId,
      traceId: "trace-1",
      memorySnapshot: [],
      workflowState: {
        taskId: task.taskId,
        type: "REACT",
        status: "DONE"
      }
    });
    expect(() => sessions.get("tenant-b", "session-1")).toThrow("session not found");
  });

  it("rejects invalid ReAct requests and prevents cross-tenant task mutations", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));

    expect(() => service.startReactTask("tenant-a", " ", "balanced", "chat-1")).toThrow("prompt is required");
    expect(() => service.startReactTask("tenant-a", "question", "balanced", " ")).toThrow("chatId is required");

    const task = service.startReactTask("tenant-a", "question", "balanced", "chat-1", undefined, "REACT_STREAM");
    expect(task.taskId).toMatch(/^task-[0-9a-f]{32}$/);
    expect(task.type).toBe("REACT_STREAM");
    expect(service.completeReactTask("tenant-b", task.taskId, "stolen answer")).toBeUndefined();
    expect(service.failReactTask("tenant-b", task.taskId, new Error("stolen failure"))).toBeUndefined();
    expect(service.getTask("tenant-a", task.taskId)?.status).toBe("PLANNING");
    expect(service.getTask("tenant-a", task.taskId)).not.toHaveProperty("finalOutput");
  });

  it("lists tenant tasks by creation time descending", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const older = service.createTask("tenant-a", "REACT", "older");
    const newer = service.createTask("tenant-a", "REACT", "newer");
    older.createdAt = "2025-01-01T00:00:00.000Z";
    older.updatedAt = "2026-01-01T00:00:00.000Z";
    newer.createdAt = "2025-02-01T00:00:00.000Z";
    newer.updatedAt = "2025-02-01T00:00:00.000Z";

    expect(service.listTasks("tenant-a", 1, 20).map((task) => task.taskId)).toEqual([newer.taskId, older.taskId]);
  });

  it("maps an invalid persisted status to FAILED", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const task = service.createTask("public", "REACT", "question");
    task.status = "NOT_A_STATE";

    expect(service.currentState(task.taskId)).toBe("FAILED");
    expect(service.currentState("missing")).toBeUndefined();
  });

  it("refuses transitions that do not start from the expected state", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const task = service.createTask("public", "REACT", "question");
    const internals = service as unknown as { transition(taskId: string, to: string, from: string): void };
    const eventsBefore = (store.workflowEvents.get(task.taskId) ?? []).length;

    internals.transition(task.taskId, "FAILED", "SEARCHING");
    expect(task.status).toBe("PLANNING");
    expect((store.workflowEvents.get(task.taskId) ?? []).length).toBe(eventsBefore);

    internals.transition(task.taskId, "SEARCHING", "PLANNING");
    expect(task.status).toBe("SEARCHING");
    expect((store.workflowEvents.get(task.taskId) ?? []).length).toBe(eventsBefore + 1);
  });

  it("records estimated input tokens on the ReAct planner step", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const task = service.startReactTask("public", "estimate my prompt tokens please", undefined, "chat-tokens");
    const detail = service.getTask("public", task.taskId);

    expect(detail?.steps[0]?.inputTokens).toBeGreaterThan(0);
  });
});

function session(): SessionState {
  return {
    id: "session-1",
    title: "Session",
    updatedAt: 1,
    modelProfile: "balanced",
    streaming: true,
    pinned: false,
    archived: false,
    workspaceId: "default",
    activeBranchId: "main",
    branches: [{
      id: "main",
      title: "Main",
      parentBranchId: null,
      parentMessageId: null,
      updatedAt: 1,
      messages: [{ id: "answer-1", role: "assistant", content: "answer", createdAt: 1 }],
      traceSteps: []
    }]
  };
}
