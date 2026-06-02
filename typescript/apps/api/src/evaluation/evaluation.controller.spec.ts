import { describe, expect, it } from "vitest";

import type { AiService } from "../ai/ai.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { EvaluationController } from "./evaluation.controller.js";

describe("EvaluationController", () => {
  it("validates dataset creation before persisting", () => {
    const controller = new EvaluationController(new PlatformStore(), fakeAiService());

    expect(controller.createDataset("public", { name: "", cases: [] })).toEqual({ ok: 0, msg: "dataset name is required" });
    expect(controller.createDataset("public", { name: "empty", cases: [] })).toEqual({ ok: 0, msg: "dataset cases are required" });
  });

  it("runs a dataset, stores metrics, and marks a baseline", async () => {
    const controller = new EvaluationController(new PlatformStore(), fakeAiService());
    const dataset = controller.createDataset("public", {
      name: "heat safety regression",
      cases: [{
        question: "What does heat safety require?",
        expectedKeywords: ["shade", "water"],
        expectedCitations: ["policy.txt"]
      }]
    });
    if (!("datasetId" in dataset)) {
      throw new Error("expected dataset creation to succeed");
    }

    const run = await controller.triggerRun("public", dataset.datasetId, { modelProfile: "balanced" });
    if (!("runId" in run)) {
      throw new Error("expected evaluation run to succeed");
    }
    const baseline = controller.baseline(run.runId);
    if (!("runId" in baseline)) {
      throw new Error("expected baseline assignment to succeed");
    }
    const report = controller.report(run.runId);

    expect(run.status).toBe("COMPLETED");
    expect(run.metrics.totalCases).toBe(1);
    expect(run.metrics.passedCases).toBe(1);
    expect(baseline?.runId).toBe(run.runId);
    expect(report).toContain("# RAG Evaluation Report");
  });
});

function fakeAiService(): AiService {
  return {
    reactChat: async () => ({
      ok: 1,
      msg: "ok",
      chatId: "eval-chat",
      answer: "Heat safety requires shade and water. [1]",
      model: "local-grounded",
      usage: { inputTokens: 10, outputTokens: 12, totalTokens: 22 },
      traceId: "trace-test",
      citations: [{
        id: "cite-1",
        source: "policy.txt",
        title: "policy.txt",
        chunkId: "job-1:0",
        snippet: "policy.txt says heat safety requires shade and water."
      }],
      evidence: ["policy.txt says heat safety requires shade and water."],
      trace: []
    })
  } as unknown as AiService;
}
