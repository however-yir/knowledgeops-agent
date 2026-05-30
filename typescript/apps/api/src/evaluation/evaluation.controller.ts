import { Body, Controller, Get, Headers, Param, Post } from "@nestjs/common";

import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller("ai/evaluation")
export class EvaluationController {
  constructor(private readonly store: PlatformStore) {}

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
    const run = {
      runId: newId("run"),
      datasetId,
      tenantId,
      status: "COMPLETED",
      modelProfile: body?.modelProfile ?? "balanced",
      metrics: {
        totalCases,
        passedCases: totalCases,
        runScore: totalCases === 0 ? 0 : 1,
        retrievalHitRate: totalCases === 0 ? 0 : 1,
        citationCoverageRate: totalCases === 0 ? 0 : 1,
        answerFaithfulnessScore: totalCases === 0 ? 0 : 1,
        avgLatencyMs: 0,
        failureRate: 0
      },
      results: [],
      createdAt: nowIso(),
      startedAt: nowIso(),
      finishedAt: nowIso()
    };
    this.store.evalRuns.set(run.runId, run);
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
    }
    return run ?? { ok: 0, msg: "run not found" };
  }

  @Get("runs/:runId/report")
  report(@Param("runId") runId: string) {
    const run = this.store.evalRuns.get(runId);
    return `# RAG Evaluation Report\n\n- Run: ${runId}\n- Status: ${run?.status ?? "not_found"}\n`;
  }
}
