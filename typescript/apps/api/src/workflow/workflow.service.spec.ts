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
});
