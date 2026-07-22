import { describe, expect, it } from "vitest";

import type { AiService } from "../ai/ai.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { EvaluationReportRenderer } from "./evaluation-report.renderer.js";
import { EvaluationController } from "./evaluation.controller.js";
import { EvaluationScorer } from "./evaluation.scorer.js";
import { EvaluationService } from "./evaluation.service.js";

describe("EvaluationController", () => {
  it("delegates Java validation failures as bad requests", () => {
    const controller = createController(new PlatformStore(), fakeAiService());

    expect(() => controller.createDataset("public", undefined)).toThrow("dataset payload is required");
    expect(() => controller.createDataset("public", { name: "", cases: [] })).toThrow("dataset name is required");
    expect(() => controller.createDataset("public", { name: "empty", cases: [] })).toThrow("dataset cases are required");
    expect(() => controller.createDataset("public", { name: "invalid", cases: [{ question: " " }] })).toThrow("case question is required");
    expect(() => controller.triggerRunFromBody("public", undefined)).toThrow("datasetId is required");
  });

  it("preserves the endpoint contracts for runs, baselines, comparisons, and reports", async () => {
    const controller = createController(new PlatformStore(), fakeAiService());
    const dataset = controller.createDataset("public", {
      name: " heat safety regression ",
      cases: [{
        question: "What does heat safety require?",
        expectedKeywords: ["shade", "water"],
        expectedCitations: ["policy.txt"]
      }]
    });

    const run = await controller.triggerRun("public", dataset.datasetId, { modelProfile: "balanced" });
    const baseline = controller.baseline("public", run.runId);
    const comparison = controller.compare("public", dataset.datasetId);
    const report = controller.report("public", run.runId);

    expect(dataset.datasetId).toMatch(/^eval-ds-[0-9a-f]{12}$/);
    expect(dataset.name).toBe("heat safety regression");
    expect(run.runId).toMatch(/^eval-run-[0-9a-f]{12}$/);
    expect(run.status).toBe("SUCCESS");
    expect(run.metrics.totalCases).toBe(1);
    expect(run.metrics.passedCases).toBe(1);
    expect(baseline.runId).toBe(run.runId);
    expect(comparison.current?.runId).toBe(run.runId);
    expect(comparison.baseline?.runId).toBe(run.runId);
    expect(report).toContain("# RAG Evaluation Report");
    expect(report).toContain("## Metrics");
    expect(report).toContain("## Cases");
    expect(report).toContain("| Run Score | 100.00% |");
  });
});

function createController(store: PlatformStore, aiService: AiService): EvaluationController {
  return new EvaluationController(new EvaluationService(
    store,
    aiService,
    new EvaluationScorer(),
    new EvaluationReportRenderer()
  ));
}

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
        source: "vector",
        title: "policy.txt",
        chunkId: "job-1:0",
        snippet: "policy.txt says heat safety requires shade and water."
      }],
      evidence: ["policy.txt says heat safety requires shade and water."],
      trace: []
    })
  } as unknown as AiService;
}
