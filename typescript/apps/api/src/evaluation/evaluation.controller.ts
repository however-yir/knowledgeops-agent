import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import type { Citation } from "@knowledgeops/shared";

import { AiService } from "../ai/ai.service.js";
import { newId, nowIso } from "../common/ids.js";
import { TenantId } from "../common/tenant-id.decorator.js";
import { normalizeTenant } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller("ai/evaluation")
export class EvaluationController {
  constructor(private readonly store: PlatformStore, private readonly aiService: AiService) {}

  @Post("datasets")
  createDataset(@TenantId() tenantId: string, @Body() body: { name: string; description?: string; cases?: Array<Record<string, unknown>> }) {
    if (!body?.name?.trim()) {
      return { ok: 0, msg: "dataset name is required" };
    }
    if (!body?.cases?.length) {
      return { ok: 0, msg: "dataset cases are required" };
    }
    const dataset = {
      datasetId: newId("ds"),
      tenantId: normalizeTenant(tenantId),
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
  listDatasets(@TenantId() tenantId: string) {
    const tenant = normalizeTenant(tenantId);
    return [...this.store.evalDatasets.values()]
      .filter((dataset) => dataset.tenantId === tenant)
      .map(({ cases: _cases, ...dataset }) => ({ ...dataset, caseCount: _cases.length }));
  }

  @Post("datasets/:datasetId/runs")
  async triggerRun(@TenantId() tenantId: string, @Param("datasetId") datasetId: string, @Body() body?: { modelProfile?: string }) {
    const tenant = normalizeTenant(tenantId);
    const dataset = this.store.evalDatasets.get(datasetId);
    if (!dataset || dataset.tenantId !== tenant) {
      return { ok: 0, msg: "dataset not found" };
    }
    const totalCases = dataset?.cases.length ?? 0;
    if (totalCases === 0) {
      return { ok: 0, msg: "dataset has no cases" };
    }
    const results = [];
    for (const [index, testCase] of (dataset?.cases ?? []).entries()) {
      const started = Date.now();
      const question = String(testCase.question ?? "");
      const chatId = String(testCase.chatId ?? `eval-${datasetId}-${index}`);
      const answer = await this.aiService.reactChat({ prompt: question, chatId, modelProfile: body?.modelProfile }, tenant);
      const expectedKeywords = toStringArray(testCase.expectedKeywords);
      const expectedCitations = toStringArray(testCase.expectedCitations);
      const forbiddenKeywords = toStringArray(testCase.forbiddenKeywords);
      const answerPool = `${answer.answer}\n${(answer.evidence ?? []).join("\n")}`.toLowerCase();
      const citationPool = citationSearchText(answer.citations ?? []);
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
      results.push({
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
        latencyMs: Date.now() - started,
        errorMessage: score >= 0.7 ? undefined : "expected keywords not sufficiently covered"
      });
    }
    const passedCases = results.filter((result) => result.status === "PASSED").length;
    const runScore = totalCases === 0 ? 0 : results.reduce((sum, result) => sum + Number(result.score), 0) / totalCases;
    const run = {
      runId: newId("run"),
      datasetId,
      tenantId: tenant,
      status: "COMPLETED",
      modelProfile: body?.modelProfile ?? "balanced",
      metrics: {
        totalCases,
        passedCases,
        runScore,
        retrievalHitRate: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.retrievalHit))),
        citationCoverageRate: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.citationCoverage))),
        answerFaithfulnessScore: totalCases === 0 ? 0 : avg(results.map((result) => Number(result.answerFaithfulness))),
        avgLatencyMs: avg(results.map((result) => Number(result.latencyMs))),
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

  @Post("runs")
  async triggerRunFromBody(@TenantId() tenantId: string, @Body() body?: { datasetId?: string; modelProfile?: string }) {
    if (!body?.datasetId?.trim()) {
      return { ok: 0, msg: "datasetId is required" };
    }
    return this.triggerRun(tenantId, body.datasetId, { modelProfile: body.modelProfile });
  }

  @Get("datasets/:datasetId/comparison")
  compare(@TenantId() tenantId: string, @Param("datasetId") datasetId: string) {
    const tenant = normalizeTenant(tenantId);
    const dataset = this.store.evalDatasets.get(datasetId);
    if (!dataset || dataset.tenantId !== tenant) {
      return { ok: 0, msg: "dataset not found" };
    }
    const runs = [...this.store.evalRuns.values()]
      .filter((run) => run.tenantId === tenant && run.datasetId === datasetId)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    const configuredBaseline = dataset.baselineRunId ? this.store.evalRuns.get(dataset.baselineRunId) : undefined;
    const baseline = configuredBaseline?.tenantId === tenant ? configuredBaseline : runs.at(-2) ?? null;
    return { dataset, baseline, current: runs.at(-1) ?? null };
  }

  @Get("runs/:runId")
  getRun(@TenantId() tenantId: string, @Param("runId") runId: string) {
    const run = this.store.evalRuns.get(runId);
    return run?.tenantId === normalizeTenant(tenantId) ? run : { ok: 0, msg: "run not found" };
  }

  @Post("runs/:runId/baseline")
  baseline(@TenantId() tenantId: string, @Param("runId") runId: string) {
    const tenant = normalizeTenant(tenantId);
    const run = this.store.evalRuns.get(runId);
    const dataset = run?.tenantId === tenant ? this.store.evalDatasets.get(run.datasetId) : undefined;
    if (run && dataset?.tenantId === tenant) {
      dataset.baselineRunId = runId;
      this.store.persist();
      return run;
    }
    return { ok: 0, msg: "run not found" };
  }

  @Get("runs/:runId/report")
  report(@TenantId() tenantId: string, @Param("runId") runId: string) {
    const candidate = this.store.evalRuns.get(runId);
    const run = candidate?.tenantId === normalizeTenant(tenantId) ? candidate : undefined;
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

function citationSearchText(citations: Citation[]): string {
  return citations
    .map((citation) => `${citation.id} ${citation.source} ${citation.title} ${citation.chunkId} ${citation.snippet}`)
    .join("\n")
    .toLowerCase();
}

function scoreFaithfulness(answer: string, citations: Citation[]): number {
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
