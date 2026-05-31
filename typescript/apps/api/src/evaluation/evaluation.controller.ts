import { Body, Controller, Get, Headers, Param, Post } from "@nestjs/common";

import { AiService } from "../ai/ai.service.js";
import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller("ai/evaluation")
export class EvaluationController {
  constructor(private readonly store: PlatformStore, private readonly aiService: AiService) {}

  @Post("datasets")
  createDataset(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: { name: string; description?: string; cases?: Array<Record<string, unknown>> }) {
    if (!body?.name?.trim()) {
      return { ok: 0, msg: "dataset name is required" };
    }
    if (!body?.cases?.length) {
      return { ok: 0, msg: "dataset cases are required" };
    }
    const dataset = {
      datasetId: newId("ds"),
      tenantId: normalizeTenant(tenantHeader),
      name: body.name.trim(),
      description: body.description,
      cases: body.cases ?? [],
      caseCount: body.cases?.length ?? 0,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    this.store.evalDatasets.set(dataset.datasetId, dataset);
    this.store.persist();
    return dataset;
  }

  @Get("datasets")
  listDatasets(@Headers(TENANT_HEADER) tenantHeader: string | undefined) {
    const tenantId = normalizeTenant(tenantHeader);
    return [...this.store.evalDatasets.values()]
      .filter((dataset) => dataset.tenantId === tenantId)
      .map(({ cases: _cases, ...dataset }) => ({ ...dataset, caseCount: _cases.length }));
  }

  @Post("datasets/:datasetId/runs")
  triggerRun(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Param("datasetId") datasetId: string, @Body() body?: { modelProfile?: string }) {
    const tenantId = normalizeTenant(tenantHeader);
    const dataset = this.store.evalDatasets.get(datasetId);
    if (!dataset) {
      return { ok: 0, msg: "dataset not found" };
    }
    const totalCases = dataset?.cases.length ?? 0;
    if (totalCases === 0) {
      return { ok: 0, msg: "dataset has no cases" };
    }
    const results = (dataset?.cases ?? []).map((testCase, index) => {
      const question = String(testCase.question ?? "");
      const chatId = String(testCase.chatId ?? `eval-${datasetId}-${index}`);
      const answer = this.aiService.reactChat({ prompt: question, chatId, modelProfile: body?.modelProfile }, tenantId);
      const expectedKeywords = toStringArray(testCase.expectedKeywords);
      const expectedCitations = toStringArray(testCase.expectedCitations);
      const forbiddenKeywords = toStringArray(testCase.forbiddenKeywords);
      const answerPool = `${answer.answer}\n${(answer.evidence ?? []).join("\n")}`.toLowerCase();
      const citationPool = (answer.citations ?? []).join("\n").toLowerCase();
      let keywordScore = expectedKeywords.length === 0
        ? (answer.answer.trim() ? 1 : 0)
        : hitRate(expectedKeywords, answerPool);
      const citationCoverage = expectedCitations.length === 0 ? 1 : hitRate(expectedCitations, citationPool);
      const forbiddenHit = forbiddenKeywords.some((keyword) => answerPool.includes(keyword.toLowerCase()));
      const retrievalHit = expectedCitations.length === 0
        ? ((answer.evidence?.length ?? 0) > 0 || keywordScore > 0 ? 1 : 0)
        : citationCoverage > 0 ? 1 : 0;
      let answerFaithfulness = scoreFaithfulness(answer.answer, answer.citations ?? []);
      if (forbiddenHit) {
        keywordScore = 0;
        answerFaithfulness = Math.min(answerFaithfulness, 0.2);
      }
      const score = round(0.30 * retrievalHit + 0.25 * citationCoverage + 0.25 * keywordScore + 0.20 * answerFaithfulness);
      return {
        resultId: newId("res"),
        caseId: String(testCase.caseId ?? `case-${index + 1}`),
        status: score >= 0.7 ? "PASSED" : "FAILED",
        question,
        answer: answer.answer,
        citations: answer.citations ?? [],
        evidence: answer.evidence ?? [],
        retrievalHit,
        citationCoverage,
        keywordScore,
        answerFaithfulness,
        score,
        latencyMs: 0,
        errorMessage: score >= 0.7 ? undefined : "expected keywords not sufficiently covered"
      };
    });
    const passedCases = results.filter((result) => result.status === "PASSED").length;
    const runScore = totalCases === 0 ? 0 : results.reduce((sum, result) => sum + Number(result.score), 0) / totalCases;
    const run = {
      runId: newId("run"),
      datasetId,
      tenantId,
      status: "COMPLETED",
      modelProfile: body?.modelProfile ?? "balanced",
      metrics: {
        totalCases,
        passedCases,
        runScore,
        retrievalHitRate: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.retrievalHit))),
        citationCoverageRate: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.citationCoverage))),
        answerFaithfulnessScore: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.answerFaithfulness))),
        avgLatencyMs: 0,
        failureRate: totalCases === 0 ? 0 : (totalCases - passedCases) / totalCases
      },
      results,
      createdAt: nowIso(),
      startedAt: nowIso(),
      finishedAt: nowIso()
    };
    this.store.evalRuns.set(run.runId, run);
    this.store.persist();
    return run;
  }

  @Get("datasets/:datasetId/comparison")
  compare(@Param("datasetId") datasetId: string) {
    const dataset = this.store.evalDatasets.get(datasetId);
    const runs = [...this.store.evalRuns.values()].filter((run) => run.datasetId === datasetId);
    const baseline = dataset?.baselineRunId ? this.store.evalRuns.get(dataset.baselineRunId) ?? null : runs.at(-2) ?? null;
    return { dataset, baseline, current: runs.at(-1) ?? null };
  }

  @Get("runs/:runId")
  getRun(@Param("runId") runId: string) {
    return this.store.evalRuns.get(runId) ?? { ok: 0, msg: "run not found" };
  }

  @Post("runs/:runId/baseline")
  baseline(@Param("runId") runId: string) {
    const run = this.store.evalRuns.get(runId);
    const dataset = run ? this.store.evalDatasets.get(run.datasetId) : undefined;
    if (run && dataset) {
      dataset.baselineRunId = runId;
      this.store.persist();
    }
    return run ?? { ok: 0, msg: "run not found" };
  }

  @Get("runs/:runId/report")
  report(@Param("runId") runId: string) {
    const run = this.store.evalRuns.get(runId);
    return [
      "# RAG Evaluation Report",
      "",
      `- Run: ${runId}`,
      `- Status: ${run?.status ?? "not_found"}`,
      `- Score: ${run?.metrics.runScore ?? 0}`,
      `- Passed Cases: ${run?.metrics.passedCases ?? 0}/${run?.metrics.totalCases ?? 0}`,
      `- Retrieval Hit Rate: ${run?.metrics.retrievalHitRate ?? 0}`,
      `- Citation Coverage Rate: ${run?.metrics.citationCoverageRate ?? 0}`,
      ""
    ].join("\n");
  }
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function avg(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function hitRate(expected: string[], actualLower: string): number {
  if (expected.length === 0) {
    return 1;
  }
  return round(expected.filter((item) => actualLower.includes(item.toLowerCase())).length / expected.length);
}

function scoreFaithfulness(answer: string, citations: string[]): number {
  if (!answer.trim()) {
    return 0;
  }
  if (citations.length === 0) {
    return 0.5;
  }
  let markers = 0;
  for (let index = 1; index <= citations.length; index += 1) {
    if (answer.includes(`[${index}]`)) {
      markers += 1;
    }
  }
  return round(Math.min(1, markers / citations.length));
}

function round(value: number): number {
  return Math.round(value * 10000) / 10000;
}
