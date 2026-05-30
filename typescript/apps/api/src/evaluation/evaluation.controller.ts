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
    const dataset = {
      datasetId: newId("ds"),
      tenantId: normalizeTenant(tenantHeader),
      name: body.name,
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
    const totalCases = dataset?.cases.length ?? 0;
    const results = (dataset?.cases ?? []).map((testCase, index) => {
      const question = String(testCase.question ?? "");
      const chatId = String(testCase.chatId ?? `eval-${datasetId}-${index}`);
      const answer = this.aiService.reactChat({ prompt: question, chatId, modelProfile: body?.modelProfile }, tenantId);
      const expectedKeywords = toStringArray(testCase.expectedKeywords);
      const forbiddenKeywords = toStringArray(testCase.forbiddenKeywords);
      const keywordScore = expectedKeywords.length === 0
        ? 1
        : expectedKeywords.filter((keyword) => answer.answer.includes(keyword)).length / expectedKeywords.length;
      const forbiddenPenalty = forbiddenKeywords.some((keyword) => answer.answer.includes(keyword)) ? 1 : 0;
      const score = Math.max(0, keywordScore - forbiddenPenalty);
      return {
        resultId: newId("res"),
        caseId: String(testCase.caseId ?? `case-${index + 1}`),
        status: score >= 0.7 ? "PASSED" : "FAILED",
        question,
        answer: answer.answer,
        citations: answer.citations ?? [],
        evidence: answer.evidence ?? [],
        retrievalHit: (answer.evidence?.length ?? 0) > 0 ? 1 : 0,
        citationCoverage: (answer.citations?.length ?? 0) > 0 ? 1 : 0,
        keywordScore,
        answerFaithfulness: answer.answer === "没有在当前知识库中检索到可用内容。" ? 0 : 1,
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
    return { dataset, baseline: null, current: runs.at(-1) ?? null };
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
    return `# RAG Evaluation Report\n\n- Run: ${runId}\n- Status: ${run?.status ?? "not_found"}\n- Score: ${run?.metrics.runScore ?? 0}\n`;
  }
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function avg(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}
