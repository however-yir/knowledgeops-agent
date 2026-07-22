import { describe, expect, it } from "vitest";

import type { AiService } from "../ai/ai.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { EvaluationReportRenderer } from "./evaluation-report.renderer.js";
import { EvaluationScorer } from "./evaluation.scorer.js";
import { EvaluationService } from "./evaluation.service.js";

describe("EvaluationService", () => {
  it("normalizes cases, assigns Java IDs, and sorts datasets by updated time", () => {
    const store = new PlatformStore();
    const service = createService(store, responseAiService());
    const older = service.createDataset("tenant-a", {
      name: " older ",
      description: " ",
      cases: [{ question: " first? " }, { caseId: " custom ", question: "second?" }]
    });
    const newer = service.createDataset("tenant-a", {
      name: "newer",
      cases: [{ question: "third?" }]
    });
    const storedOlder = store.evalDatasets.get(older.datasetId);
    const storedNewer = store.evalDatasets.get(newer.datasetId);
    if (!storedOlder || !storedNewer) {
      throw new Error("expected stored datasets");
    }
    storedOlder.updatedAt = "2026-01-01T00:00:00";
    storedNewer.updatedAt = "2026-01-02T00:00:00";

    expect(older.datasetId).toMatch(/^eval-ds-[0-9a-f]{12}$/);
    expect(older).toMatchObject({ tenantId: "tenant-a", name: "older", description: "", caseCount: 2 });
    expect(storedOlder.cases).toMatchObject([
      { caseId: "case-001", question: "first?", category: "", chatId: "" },
      { caseId: "custom", question: "second?" }
    ]);
    expect(service.listDatasets("tenant-a").map((item) => item.datasetId)).toEqual([newer.datasetId, older.datasetId]);
    expect(service.listDatasets("tenant-b")).toEqual([]);
  });

  it("keeps low-score execution successful and counts only execution failures in failureRate", async () => {
    const store = new PlatformStore();
    const calls: Array<{ chatId?: string; historyType?: string }> = [];
    let callIndex = 0;
    const service = createService(store, {
      reactChat: async (request: { chatId?: string }, _tenant: string, historyType: string) => {
        calls.push({ chatId: request.chatId, historyType });
        callIndex += 1;
        if (callIndex === 2) {
          throw new Error("provider unavailable");
        }
        return response({ answer: "unrelated but valid answer", evidence: [] });
      }
    } as unknown as AiService);
    const dataset = service.createDataset("tenant-a", {
      name: "status vectors",
      cases: [
        { chatId: " explicit-chat ", question: "low score", expectedKeywords: ["missing"] },
        { question: "execution failure" }
      ]
    });

    const run = await service.triggerRun("tenant-a", dataset.datasetId, { chatIdPrefix: " batch " });

    expect(calls).toEqual([
      { chatId: "explicit-chat", historyType: "eval" },
      { chatId: "batch-002", historyType: "eval" }
    ]);
    expect(run.status).toBe("SUCCESS");
    expect(run.results[0]).toMatchObject({ status: "SUCCESS", errorMessage: "" });
    expect(run.results[0]?.score).toBeLessThan(0.7);
    expect(run.results[1]).toMatchObject({ status: "FAILED", errorMessage: "provider unavailable" });
    expect(run.metrics).toMatchObject({ totalCases: 2, passedCases: 0, failureRate: 0.5 });
  });

  it("deduplicates Java citation strings and uses dataset chat fallback", async () => {
    const store = new PlatformStore();
    const chatIds: string[] = [];
    const service = createService(store, {
      reactChat: async (request: { chatId?: string }) => {
        chatIds.push(request.chatId ?? "");
        return response({
          answer: "policy answer [1]",
          citations: [citation(), citation()],
          evidence: ["policy evidence"]
        });
      }
    } as unknown as AiService);
    const dataset = service.createDataset("tenant-a", {
      name: "citations",
      cases: [{ question: "policy?", expectedKeywords: ["policy"], expectedCitations: ["vector:policy.txt:chunk-1"] }]
    });

    const run = await service.triggerRun("tenant-a", dataset.datasetId);

    expect(chatIds).toEqual([dataset.datasetId]);
    expect(run.results[0]?.resultId).toMatch(/^eval-result-[0-9a-f]{12}$/);
    expect(run.results[0]?.citations).toEqual(["vector:policy.txt:chunk-1"]);
    expect(run.results[0]).toMatchObject({ status: "SUCCESS", score: 1 });
    expect(run.metrics.passedCases).toBe(1);
  });

  it("uses configured baselines and otherwise compares the two latest runs", async () => {
    const store = new PlatformStore();
    const service = createService(store, responseAiService());
    const dataset = service.createDataset("tenant-a", { name: "comparison", cases: [{ question: "q" }] });
    const first = await service.triggerRun("tenant-a", dataset.datasetId);
    const second = await service.triggerRun("tenant-a", dataset.datasetId);

    expect(service.compareLatest("tenant-a", dataset.datasetId)).toMatchObject({
      baseline: { runId: first.runId },
      current: { runId: second.runId }
    });

    service.markBaseline("tenant-a", second.runId);
    expect(service.compareLatest("tenant-a", dataset.datasetId)).toMatchObject({
      baseline: { runId: second.runId },
      current: { runId: second.runId }
    });
    expect(() => service.getRun("tenant-b", first.runId)).toThrow("run not found");
    expect(() => service.compareLatest("tenant-b", dataset.datasetId)).toThrow("dataset not found");
  });
});

function createService(store: PlatformStore, aiService: AiService): EvaluationService {
  return new EvaluationService(store, aiService, new EvaluationScorer(), new EvaluationReportRenderer());
}

function responseAiService(): AiService {
  return { reactChat: async () => response() } as unknown as AiService;
}

function response(overrides: Record<string, unknown> = {}) {
  return {
    ok: 1,
    msg: "ok",
    chatId: "eval-chat",
    answer: "answer [1]",
    model: "test",
    usage: { inputTokens: 1, outputTokens: 1, totalTokens: 2 },
    traceId: "trace",
    citations: [citation()],
    evidence: ["answer evidence"],
    trace: [],
    ...overrides
  };
}

function citation() {
  return {
    id: "cite-1",
    source: "vector",
    title: "policy.txt",
    chunkId: "chunk-1",
    snippet: "policy evidence"
  };
}
