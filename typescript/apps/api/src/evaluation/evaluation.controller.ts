import { BadRequestException, Body, Controller, Get, Param, Post, Res } from "@nestjs/common";
import type { FastifyReply } from "fastify";

import { TenantId } from "../common/tenant-id.decorator.js";
import {
  type EvaluationDatasetPayload,
  type EvaluationRunRequest,
  EvaluationService
} from "./evaluation.service.js";

@Controller("ai/evaluation")
export class EvaluationController {
  constructor(private readonly evaluationService: EvaluationService) {}

  @Post("datasets")
  createDataset(@TenantId() tenantId: string, @Body() body?: EvaluationDatasetPayload) {
    return this.evaluationService.createDataset(tenantId, body);
  }

  @Get("datasets")
  listDatasets(@TenantId() tenantId: string) {
    return this.evaluationService.listDatasets(tenantId);
  }

  @Post("datasets/:datasetId/runs")
  triggerRun(
    @TenantId() tenantId: string,
    @Param("datasetId") datasetId: string,
    @Body() body?: EvaluationRunRequest
  ) {
    return this.evaluationService.triggerRun(tenantId, datasetId, body);
  }

  @Post("runs")
  triggerRunFromBody(@TenantId() tenantId: string, @Body() body?: EvaluationRunRequest) {
    if (!body?.datasetId?.trim()) {
      throw new BadRequestException("datasetId is required");
    }
    return this.evaluationService.triggerRun(tenantId, body.datasetId, body);
  }

  @Get("datasets/:datasetId/comparison")
  compare(@TenantId() tenantId: string, @Param("datasetId") datasetId: string) {
    return this.evaluationService.compareLatest(tenantId, datasetId);
  }

  @Get("runs/:runId")
  getRun(@TenantId() tenantId: string, @Param("runId") runId: string) {
    return this.evaluationService.getRun(tenantId, runId);
  }

  @Post("runs/:runId/baseline")
  baseline(@TenantId() tenantId: string, @Param("runId") runId: string) {
    return this.evaluationService.markBaseline(tenantId, runId);
  }

  @Get("runs/:runId/report")
  report(
    @TenantId() tenantId: string,
    @Param("runId") runId: string,
    @Res({ passthrough: true }) reply?: FastifyReply
  ) {
    reply?.header("Content-Type", "text/markdown;charset=UTF-8");
    reply?.header("Content-Disposition", `attachment; filename="rag-evaluation-${runId}.md"`);
    return this.evaluationService.exportReport(tenantId, runId);
  }
}
