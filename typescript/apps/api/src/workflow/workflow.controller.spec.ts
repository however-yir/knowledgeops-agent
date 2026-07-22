import { NotFoundException } from "@nestjs/common";
import { describe, expect, it, vi } from "vitest";

import type { AiService } from "../ai/ai.service.js";
import { RetrievalService } from "../ai/retrieval.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { WorkflowController } from "./workflow.controller.js";
import { WorkflowService } from "./workflow.service.js";

describe("WorkflowController", () => {
  it("returns the Java deep research result contract", async () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const controller = new WorkflowController(service, {} as AiService);

    const result = await controller.createResearch("tenant-a", { topic: "Heat safety" });

    expect(result).toMatchObject({
      taskId: expect.stringMatching(/^task-[0-9a-f]{32}$/),
      topic: "Heat safety",
      status: "DONE",
      report: expect.stringContaining("## 1. 执行摘要")
    });
    expect(result).not.toHaveProperty("ok");
    expect(result).not.toHaveProperty("task");
  });

  it("rejects missing POST bodies with HTTP 400 exceptions", async () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const controller = new WorkflowController(service, {} as AiService);

    await expect(controller.createResearch("tenant-a", undefined)).rejects.toMatchObject({ status: 400 });
    await expect(controller.workflowReact("tenant-a", undefined)).rejects.toMatchObject({ status: 400 });
    await expect(controller.workflowReactStream("tenant-a", undefined)).rejects.toMatchObject({ status: 400 });
    expect(store.workflowTasks.size).toBe(0);
  });

  it("throws HTTP 404 exceptions for missing task and report", () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const controller = new WorkflowController(service, {} as AiService);

    expect(() => controller.getTask("tenant-a", "missing")).toThrow(NotFoundException);
    expect(() => controller.getResearchReport("tenant-a", "missing")).toThrow(NotFoundException);
  });

  it("keeps an error-only stream task nonterminal like Java", async () => {
    const store = new PlatformStore();
    const service = new WorkflowService(store, new RetrievalService(store), new MetricsService(store));
    const stream = 'event: error\ndata: {"message":"provider failed"}\n\n';
    const aiService = { reactChatStream: vi.fn().mockResolvedValue(stream) } as unknown as AiService;
    const controller = new WorkflowController(service, aiService);

    await expect(controller.workflowReactStream("tenant-a", { chatId: "chat-1", prompt: "question" })).resolves.toBe(stream);

    expect([...store.workflowTasks.values()]).toHaveLength(1);
    expect([...store.workflowTasks.values()][0]).toMatchObject({ type: "REACT_STREAM", status: "PLANNING" });
  });
});
