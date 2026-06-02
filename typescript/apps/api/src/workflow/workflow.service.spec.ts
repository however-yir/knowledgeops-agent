import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { WorkflowService } from "./workflow.service.js";

describe("WorkflowService", () => {
  it("runs deep research through task, step, and event lifecycle", () => {
    const store = new PlatformStore();
    const retrieval = new RetrievalService(store);
    retrieval.addDocumentChunks({
      tenantId: "public",
      chatId: "research_1",
      jobId: "job-1",
      fileName: "policy.txt",
      sourceType: "TEXT",
      text: "Heat safety requires shade, water, rest breaks, and supervisor escalation."
    });
    const service = new WorkflowService(store, retrieval, new MetricsService(store));

    const task = service.executeResearch("public", "Heat safety");

    expect(task.status).toBe("DONE");
    expect(task.finalOutput).toContain("Research Report");
    expect(service.getEvents(task.taskId).length).toBeGreaterThan(2);
    expect(store.workflowSteps.get(task.taskId)?.length).toBeGreaterThan(1);
  });

  it("lists workflow tasks only for the requested tenant", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));

    service.createTask("public", "DEEP_RESEARCH", "public topic");
    service.createTask("acme", "DEEP_RESEARCH", "acme topic");

    expect(service.listTasks("public", 1, 20)).toHaveLength(1);
    expect(service.listTasks("public", 1, 20)[0]?.tenantId).toBe("public");
    expect(service.listTasks("acme", 1, 20)[0]?.tenantId).toBe("acme");
  });

  it("processes one queued research task at a time", async () => {
    const store = new PlatformStore();
    const retrieval = new RetrievalService(store);
    const service = new WorkflowService(store, retrieval, new MetricsService(store));
    const task = service.enqueueResearch("public", "queued heat safety");

    const processed = await service.processQueuedTasks();

    expect(processed).toBe(1);
    expect(service.getTask(task.taskId)?.status).toBe("DONE");
    expect(service.getTask(task.taskId)?.events.some((event) => event.eventType === "TASK_COMPLETED")).toBe(true);
  });
});
