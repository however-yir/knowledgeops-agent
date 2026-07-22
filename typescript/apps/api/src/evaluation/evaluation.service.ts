import { randomBytes } from "node:crypto";

import { BadRequestException, Injectable } from "@nestjs/common";
import type { Citation } from "@knowledgeops/shared";

import { AiService } from "../ai/ai.service.js";
import { normalizeTenant } from "../common/tenant.js";
import { type EvalDataset, type EvalRun, PlatformStore } from "../platform/platform.store.js";
import { EvaluationReportRenderer } from "./evaluation-report.renderer.js";
import { EvaluationScorer, roundEvaluation } from "./evaluation.scorer.js";

const PASS_THRESHOLD = 0.70;

export interface EvaluationCasePayload {
  caseId?: string;
  category?: string;
  chatId?: string;
  question?: string;
  expectedCitations?: string[];
  expectedKeywords?: string[];
  forbiddenKeywords?: string[];
}

export interface EvaluationDatasetPayload {
  name?: string;
  description?: string;
  cases?: Array<EvaluationCasePayload | null>;
}

export interface EvaluationRunRequest {
  datasetId?: string;
  modelProfile?: string;
  chatIdPrefix?: string;
}

export interface EvaluationDatasetView {
  datasetId: string;
  tenantId: string;
  name: string;
  description: string;
  baselineRunId: string | null;
  caseCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface EvaluationMetrics {
  [key: string]: number;
  totalCases: number;
  passedCases: number;
  runScore: number;
  retrievalHitRate: number;
  citationCoverageRate: number;
  answerFaithfulnessScore: number;
  avgLatencyMs: number;
  failureRate: number;
}

export interface EvaluationResultView {
  resultId: string;
  caseId: string;
  status: string;
  question: string;
  answer: string;
  citations: string[];
  evidence: string[];
  retrievalHit: number;
  citationCoverage: number;
  keywordScore: number;
  answerFaithfulness: number;
  score: number;
  latencyMs: number;
  errorMessage: string;
}

export interface EvaluationRunView {
  runId: string;
  datasetId: string;
  tenantId: string;
  status: string;
  modelProfile: string;
  metrics: EvaluationMetrics;
  results: EvaluationResultView[];
  errorMessage: string | null;
  startedAt: string;
  finishedAt: string;
  createdAt: string;
}

export interface EvaluationComparisonView {
  dataset: EvaluationDatasetView;
  baseline: EvaluationRunView | null;
  current: EvaluationRunView | null;
}

@Injectable()
export class EvaluationService {
  constructor(
    private readonly store: PlatformStore,
    private readonly aiService: AiService,
    private readonly scorer: EvaluationScorer,
    private readonly reportRenderer: EvaluationReportRenderer
  ) {}

  createDataset(tenantId: string, request: EvaluationDatasetPayload | null | undefined): EvaluationDatasetView {
    if (!request) {
      throw new BadRequestException("dataset payload is required");
    }
    if (!request.name?.trim()) {
      throw new BadRequestException("dataset name is required");
    }
    if (!request.cases?.length) {
      throw new BadRequestException("dataset cases are required");
    }

    const cases = request.cases.map((item, index) => normalizeCase(item, index));
    const tenant = normalizeTenant(tenantId);
    const now = localDateTime();
    const dataset: EvalDataset = {
      datasetId: evaluationId("eval-ds"),
      tenantId: tenant,
      name: request.name.trim(),
      description: nonBlankOrEmpty(request.description),
      cases,
      createdAt: now,
      updatedAt: now
    };
    this.store.evalDatasets.set(dataset.datasetId, dataset);
    this.store.persist();
    return datasetView(dataset);
  }

  listDatasets(tenantId: string): EvaluationDatasetView[] {
    const tenant = normalizeTenant(tenantId);
    return [...this.store.evalDatasets.values()]
      .filter((dataset) => dataset.tenantId === tenant)
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .map(datasetView);
  }

  async triggerRun(
    tenantId: string,
    datasetId: string,
    request?: EvaluationRunRequest | null
  ): Promise<EvaluationRunView> {
    const tenant = normalizeTenant(tenantId);
    const dataset = this.requireDataset(tenant, datasetId);
    if (dataset.cases.length === 0) {
      throw new BadRequestException("dataset has no cases");
    }

    const now = localDateTime();
    const modelProfile = request?.modelProfile?.trim() || "balanced";
    const run: EvalRun = {
      runId: evaluationId("eval-run"),
      datasetId: dataset.datasetId,
      tenantId: tenant,
      status: "RUNNING",
      modelProfile,
      metrics: emptyMetrics(dataset.cases.length),
      results: [],
      createdAt: now,
      startedAt: now
    };
    this.store.evalRuns.set(run.runId, run);
    this.store.persist();

    const results: EvaluationResultView[] = [];
    for (const [index, evalCase] of dataset.cases.entries()) {
      results.push(await this.runCase(tenant, run.runId, dataset, evalCase, request, index));
    }

    run.status = "SUCCESS";
    run.metrics = summarize(results);
    run.results = results.map((result) => ({ ...result }));
    run.finishedAt = localDateTime();
    this.store.persist();
    return runView(run);
  }

  getRun(tenantId: string, runId: string): EvaluationRunView {
    return runView(this.requireRun(normalizeTenant(tenantId), runId));
  }

  markBaseline(tenantId: string, runId: string): EvaluationRunView {
    const tenant = normalizeTenant(tenantId);
    const run = this.requireRun(tenant, runId);
    const dataset = this.store.evalDatasets.get(run.datasetId);
    if (!dataset || dataset.tenantId !== tenant) {
      throw new BadRequestException("dataset not found");
    }
    dataset.baselineRunId = run.runId;
    dataset.updatedAt = localDateTime();
    this.store.persist();
    return runView(run);
  }

  compareLatest(tenantId: string, datasetId: string): EvaluationComparisonView {
    const tenant = normalizeTenant(tenantId);
    const dataset = this.requireDataset(tenant, datasetId);
    const recent = [...this.store.evalRuns.values()]
      .filter((run) => run.tenantId === tenant && run.datasetId === dataset.datasetId)
      .map((run, index) => ({ run, index }))
      .sort((left, right) => right.run.createdAt.localeCompare(left.run.createdAt) || right.index - left.index)
      .slice(0, 2)
      .map(({ run }) => run);
    const current = recent[0];

    let baseline: EvalRun | undefined;
    if (dataset.baselineRunId) {
      const candidate = this.store.evalRuns.get(dataset.baselineRunId);
      if (candidate?.tenantId === tenant) {
        baseline = candidate;
      }
    }
    baseline ??= recent[1];

    return {
      dataset: datasetView(dataset),
      baseline: baseline ? runView(baseline) : null,
      current: current ? runView(current) : null
    };
  }

  exportReport(tenantId: string, runId: string): string {
    return this.reportRenderer.render(this.getRun(tenantId, runId));
  }

  private async runCase(
    tenant: string,
    runId: string,
    dataset: EvalDataset,
    evalCase: Record<string, unknown>,
    request: EvaluationRunRequest | null | undefined,
    index: number
  ): Promise<EvaluationResultView> {
    const started = process.hrtime.bigint();
    let status = "SUCCESS";
    let answer = "";
    let errorMessage = "";
    let citations: string[] = [];
    let evidence: string[] = [];

    try {
      const chatId = resolveChatId(dataset.datasetId, evalCase, request, index);
      const result = await this.aiService.reactChat({
        prompt: String(evalCase.question ?? ""),
        chatId,
        modelProfile: request?.modelProfile
      }, tenant, "eval");
      answer = nonBlankOrEmpty(result.answer);
      citations = citationStrings(result.citations ?? []);
      evidence = stringList(result.evidence).filter((item) => item.trim());
      if (!answer.trim()) {
        status = "FAILED";
        errorMessage = "empty answer";
      }
    } catch (error) {
      status = "FAILED";
      errorMessage = error instanceof Error && error.message.trim()
        ? error.message
        : "evaluation case failed";
    }

    const latencyMs = Number((process.hrtime.bigint() - started) / 1_000_000n);
    const scores = this.scorer.scoreCase(evalCase, answer, citations, evidence, status === "FAILED");
    return {
      resultId: evaluationId("eval-result"),
      caseId: String(evalCase.caseId ?? ""),
      status,
      question: String(evalCase.question ?? ""),
      answer,
      citations,
      evidence,
      ...scores,
      latencyMs,
      errorMessage
    };
  }

  private requireDataset(tenant: string, datasetId: string): EvalDataset {
    if (!datasetId?.trim()) {
      throw new BadRequestException("dataset id is required");
    }
    const dataset = this.store.evalDatasets.get(datasetId.trim());
    if (!dataset || dataset.tenantId !== tenant) {
      throw new BadRequestException("dataset not found");
    }
    return dataset;
  }

  private requireRun(tenant: string, runId: string): EvalRun {
    if (!runId?.trim()) {
      throw new BadRequestException("run id is required");
    }
    const run = this.store.evalRuns.get(runId.trim());
    if (!run || run.tenantId !== tenant) {
      throw new BadRequestException("run not found");
    }
    return run;
  }
}

function normalizeCase(item: EvaluationCasePayload | null, index: number): Record<string, unknown> {
  if (!item?.question?.trim()) {
    throw new BadRequestException("case question is required");
  }
  return {
    caseId: item.caseId?.trim() || `case-${String(index + 1).padStart(3, "0")}`,
    category: nonBlankOrEmpty(item.category),
    chatId: nonBlankOrEmpty(item.chatId),
    question: item.question.trim(),
    expectedCitations: stringList(item.expectedCitations),
    expectedKeywords: stringList(item.expectedKeywords),
    forbiddenKeywords: stringList(item.forbiddenKeywords)
  };
}

function resolveChatId(
  datasetId: string,
  evalCase: Record<string, unknown>,
  request: EvaluationRunRequest | null | undefined,
  index: number
): string {
  const caseChatId = typeof evalCase.chatId === "string" ? evalCase.chatId.trim() : "";
  if (caseChatId) {
    return caseChatId;
  }
  const prefix = request?.chatIdPrefix?.trim();
  return prefix ? `${prefix}-${String(index + 1).padStart(3, "0")}` : datasetId;
}

function citationStrings(citations: Citation[]): string[] {
  const values = new Set<string>();
  for (const citation of citations) {
    if (!citation) {
      continue;
    }
    const sourceType = nonBlankOrEmpty((citation as Citation & { sourceType?: string }).sourceType ?? citation.source);
    const title = nonBlankOrEmpty(citation.title);
    const chunkId = nonBlankOrEmpty(citation.chunkId);
    const text = `${sourceType}:${title}:${chunkId}`;
    if (text.replaceAll(":", "").trim()) {
      values.add(text);
    }
  }
  return [...values];
}

function summarize(results: EvaluationResultView[]): EvaluationMetrics {
  const totalCases = results.length;
  const passedCases = results
    .filter((result) => result.status === "SUCCESS" && result.score >= PASS_THRESHOLD)
    .length;
  const denominator = Math.max(1, totalCases);
  return {
    totalCases,
    passedCases,
    runScore: roundEvaluation(average(results.map((result) => result.score))),
    retrievalHitRate: roundEvaluation(average(results.map((result) => result.retrievalHit))),
    citationCoverageRate: roundEvaluation(average(results.map((result) => result.citationCoverage))),
    answerFaithfulnessScore: roundEvaluation(average(results.map((result) => result.answerFaithfulness))),
    avgLatencyMs: roundEvaluation(average(results.map((result) => result.latencyMs))),
    failureRate: roundEvaluation(results.filter((result) => result.status !== "SUCCESS").length / denominator)
  };
}

function emptyMetrics(totalCases: number): EvaluationMetrics {
  return {
    totalCases,
    passedCases: 0,
    runScore: 0,
    retrievalHitRate: 0,
    citationCoverageRate: 0,
    answerFaithfulnessScore: 0,
    avgLatencyMs: 0,
    failureRate: 0
  };
}

function average(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function datasetView(dataset: EvalDataset): EvaluationDatasetView {
  return {
    datasetId: dataset.datasetId,
    tenantId: dataset.tenantId,
    name: dataset.name,
    description: dataset.description ?? "",
    baselineRunId: dataset.baselineRunId ?? null,
    caseCount: dataset.cases.length,
    createdAt: dataset.createdAt,
    updatedAt: dataset.updatedAt
  };
}

function runView(run: EvalRun): EvaluationRunView {
  return {
    runId: run.runId,
    datasetId: run.datasetId,
    tenantId: run.tenantId,
    status: run.status,
    modelProfile: run.modelProfile,
    metrics: metricsView(run.metrics),
    results: run.results.map(resultView),
    errorMessage: run.errorMessage ?? null,
    startedAt: run.startedAt ?? "",
    finishedAt: run.finishedAt ?? "",
    createdAt: run.createdAt
  };
}

function metricsView(metrics: Record<string, number>): EvaluationMetrics {
  return {
    totalCases: numberOrZero(metrics.totalCases),
    passedCases: numberOrZero(metrics.passedCases),
    runScore: numberOrZero(metrics.runScore),
    retrievalHitRate: numberOrZero(metrics.retrievalHitRate),
    citationCoverageRate: numberOrZero(metrics.citationCoverageRate),
    answerFaithfulnessScore: numberOrZero(metrics.answerFaithfulnessScore),
    avgLatencyMs: numberOrZero(metrics.avgLatencyMs),
    failureRate: numberOrZero(metrics.failureRate)
  };
}

function resultView(result: Record<string, unknown>): EvaluationResultView {
  return {
    resultId: String(result.resultId ?? ""),
    caseId: String(result.caseId ?? ""),
    status: String(result.status ?? ""),
    question: String(result.question ?? ""),
    answer: String(result.answer ?? ""),
    citations: stringList(result.citations),
    evidence: stringList(result.evidence),
    retrievalHit: numberOrZero(result.retrievalHit),
    citationCoverage: numberOrZero(result.citationCoverage),
    keywordScore: numberOrZero(result.keywordScore),
    answerFaithfulness: numberOrZero(result.answerFaithfulness),
    score: numberOrZero(result.score),
    latencyMs: numberOrZero(result.latencyMs),
    errorMessage: String(result.errorMessage ?? "")
  };
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => typeof item === "string" ? item : "")
    : [];
}

function numberOrZero(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function nonBlankOrEmpty(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "";
}

function evaluationId(prefix: string): string {
  return `${prefix}-${randomBytes(6).toString("hex")}`;
}

function localDateTime(date = new Date()): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().replace(/Z$/, "");
}
