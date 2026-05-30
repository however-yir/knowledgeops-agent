import { Controller, Get, Headers, NotFoundException, Param, Post, Query, Req } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import { buffer } from "node:stream/consumers";

import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { IngestionService } from "./ingestion.service.js";

@Controller()
export class IngestionController {
  constructor(private readonly ingestionService: IngestionService) {}

  @Post(["ingestion/upload/:chatId", "ai/pdf/upload/:chatId"])
  async upload(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Param("chatId") chatId: string, @Req() request: FastifyRequest) {
    const maybeMultipart = request.isMultipart();
    const file = maybeMultipart ? await request.file() : undefined;
    const content = file ? await buffer(file.file) : Buffer.from("");
    const idempotencyHeader = request.headers["x-idempotency-key"];
    const idempotencyKey = Array.isArray(idempotencyHeader) ? idempotencyHeader[0] : idempotencyHeader;
    const tenantId = normalizeTenant(tenantHeader);
    const job = await this.ingestionService.createJob({
      tenantId,
      chatId,
      sourceName: file?.filename ?? "document.txt",
      content,
      idempotencyKey
    });
    this.ingestionService.processOne(tenantId, job.jobId);
    return { ok: 1, msg: "accepted", job: this.ingestionService.getJob(tenantId, job.jobId) ?? job };
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
