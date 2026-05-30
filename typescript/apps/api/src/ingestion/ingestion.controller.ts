import { Controller, Get, Headers, NotFoundException, Param, Post, Query, Req } from "@nestjs/common";
import type { FastifyRequest } from "fastify";

import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { IngestionService } from "./ingestion.service.js";

@Controller()
export class IngestionController {
  constructor(private readonly ingestionService: IngestionService) {}

  @Post(["ingestion/upload/:chatId", "ai/pdf/upload/:chatId"])
  async upload(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Param("chatId") chatId: string, @Req() request: FastifyRequest) {
    const maybeMultipart = request.isMultipart();
    const file = maybeMultipart ? await request.file() : undefined;
    const job = this.ingestionService.createJob(normalizeTenant(tenantHeader), chatId, file?.filename ?? "document.pdf");
    return { ok: 1, msg: "accepted", job };
  }

  @Get("ingestion/jobs/:jobId")
  getJob(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Param("jobId") jobId: string) {
    const job = this.ingestionService.getJob(normalizeTenant(tenantHeader), jobId);
    if (!job) {
      throw new NotFoundException("job not found");
    }
    return job;
  }

  @Get("ingestion/jobs")
  listJobs(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Query("chatId") chatId: string, @Query("limit") limit = "20") {
    return this.ingestionService.listByChatId(normalizeTenant(tenantHeader), chatId, Number(limit));
  }

  @Post("ingestion/jobs/process")
  processOne(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Query("jobId") jobId?: string) {
    const msg = this.ingestionService.processOne(normalizeTenant(tenantHeader), jobId);
    return { ok: 1, msg, job: null };
  }
}
