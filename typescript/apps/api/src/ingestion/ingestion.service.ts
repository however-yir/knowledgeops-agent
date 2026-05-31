import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";

import { Injectable } from "@nestjs/common";
import type { IngestionJob } from "@knowledgeops/shared";

import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { env } from "../config/env.js";
import { IngestionJobRecord, PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class IngestionService {
  constructor(private readonly store: PlatformStore, private readonly retrievalService: RetrievalService) {}

  async createJob(params: {
    tenantId: string;
    chatId: string;
    sourceName?: string;
    content: Buffer;
    idempotencyKey?: string;
    traceId?: string;
  }): Promise<IngestionJob> {
    if (!params.chatId?.trim()) {
      throw new Error("chatId is required");
    }
    if (!params.content.length) {
      throw new Error("file is required");
    }
    const sourceName = sanitizeFilename(params.sourceName || "document.txt");
    scanFile(sourceName, params.content);
    const contentHash = sha256Buffer(params.content);
    const idempotencyKey = params.idempotencyKey?.trim()
      ? `client:${params.idempotencyKey.trim()}`
      : `auto:${sha256Text(`${params.tenantId}|${params.chatId}|${contentHash}`)}`;
    const existingJobId = this.store.idempotencyIndex.get(`${params.tenantId}:${idempotencyKey}`);
    if (existingJobId) {
      const existing = this.store.ingestionJobs.get(`${params.tenantId}:${existingJobId}`);
      if (existing) {
        return toPublicJob(existing);
      }
    }

    const jobId = newId("job");
    const now = nowIso();
    const filePath = await persistUpload(jobId, sourceName, params.content);
    const job: IngestionJobRecord = {
      jobId,
      tenantId: params.tenantId,
      chatId: params.chatId,
      sourceName,
      sourceType: inferSourceType(sourceName),
      filePath,
      idempotencyKey,
      contentHash,
      rawText: extractText(sourceName, params.content),
      status: "PENDING",
      attemptCount: 0,
      maxRetries: env.APP_INGESTION_MAX_RETRIES,
      traceId: params.traceId ?? "",
      queueBackend: env.APP_INGESTION_QUEUE_BACKEND,
      createdAt: now,
      updatedAt: now
    };
    this.store.ingestionJobs.set(`${params.tenantId}:${job.jobId}`, job);
    this.store.idempotencyIndex.set(`${params.tenantId}:${idempotencyKey}`, job.jobId);
    this.store.incrementMetric("ingestion_jobs_submitted_total", { source: job.sourceType, tenant: params.tenantId });
    this.store.persist();
    return toPublicJob(job);
  }

  getJob(tenantId: string, jobId: string): IngestionJob | undefined {
    const job = this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
    return job ? toPublicJob(job) : undefined;
  }

  listByChatId(tenantId: string, chatId: string, limit: number): IngestionJob[] {
    return [...this.store.ingestionJobs.entries()]
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && (!chatId || job.chatId === chatId))
      .map(([, job]) => toPublicJob(job))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, Math.max(1, Math.min(limit, 100)));
  }

  latestFileForChat(tenantId: string, chatId: string): { filePath: string; sourceName: string } | undefined {
    const latest = [...this.store.ingestionJobs.values()]
      .filter((job) => job.tenantId === tenantId && job.chatId === chatId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
    return latest ? { filePath: latest.filePath, sourceName: latest.sourceName } : undefined;
  }

  processOne(tenantId: string, jobId?: string): string {
    const candidates = [...this.store.ingestionJobs.entries()]
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && (!jobId || job.jobId === jobId) && isReady(job))
      .sort(([, a], [, b]) => a.createdAt.localeCompare(b.createdAt));
    const [, job] = candidates[0] ?? [];
    if (!job) {
      return "empty";
    }
    job.status = "RUNNING";
    job.startedAt = job.startedAt ?? nowIso();
    job.updatedAt = nowIso();
    try {
      this.retrievalService.addDocumentChunks({
        tenantId: job.tenantId,
        chatId: job.chatId,
        jobId: job.jobId,
        fileName: job.sourceName,
        sourceType: job.sourceType,
        text: job.rawText
      });
      job.status = "SUCCEEDED";
      job.finishedAt = nowIso();
      job.errorMessage = undefined;
      this.store.incrementMetric("ingestion_jobs_finished_total", { status: "succeeded", tenant: tenantId });
    } catch (error) {
      job.attemptCount += 1;
      job.errorMessage = truncateError(error instanceof Error ? error.message : String(error));
      job.status = job.attemptCount < job.maxRetries ? "RETRY" : "FAILED";
      job.nextRetryAt = job.status === "RETRY"
        ? new Date(Date.now() + env.APP_INGESTION_BASE_DELAY_SECONDS * Math.max(1, job.attemptCount) * 1000).toISOString()
        : undefined;
      job.finishedAt = nowIso();
      this.store.incrementMetric("ingestion_jobs_finished_total", { status: job.status.toLowerCase(), tenant: tenantId });
    }
    job.updatedAt = nowIso();
    this.store.persist();
    return "processed";
  }

  enqueueReadyRetries(tenantId: string, limit = 50): number {
    const ready = [...this.store.ingestionJobs.values()]
      .filter((job) => job.tenantId === tenantId && job.status === "RETRY" && (!job.nextRetryAt || Date.parse(job.nextRetryAt) <= Date.now()))
      .slice(0, Math.max(1, limit));
    for (const job of ready) {
      job.status = "QUEUED";
      job.updatedAt = nowIso();
    }
    this.store.persist();
    return ready.length;
  }
}

function toPublicJob(job: IngestionJobRecord): IngestionJob {
  return {
    jobId: job.jobId,
    chatId: job.chatId,
    sourceName: job.sourceName,
    status: job.status,
    attemptCount: job.attemptCount,
    maxRetries: job.maxRetries,
    errorMessage: job.errorMessage,
    traceId: job.traceId,
    queueBackend: job.queueBackend,
    createdAt: job.createdAt,
    startedAt: job.startedAt,
    finishedAt: job.finishedAt
  };
}

async function persistUpload(jobId: string, sourceName: string, content: Buffer): Promise<string> {
  await mkdir(env.APP_INGESTION_STORAGE_DIR, { recursive: true });
  const filePath = join(env.APP_INGESTION_STORAGE_DIR, `${jobId}_${sourceName}`);
  await writeFile(filePath, content);
  return filePath;
}

function scanFile(sourceName: string, content: Buffer): void {
  const lower = sourceName.toLowerCase();
  const head = content.subarray(0, 8192).toString("latin1");
  if (head.includes("EICAR-STANDARD-ANTIVIRUS-TEST-FILE")) {
    throw new Error("file blocked by malware signature");
  }
  if (lower.endsWith(".pdf") && !head.startsWith("%PDF-")) {
    throw new Error("invalid pdf header");
  }
}

function extractText(sourceName: string, content: Buffer): string {
  const lower = sourceName.toLowerCase();
  const raw = content.toString(lower.endsWith(".pdf") ? "latin1" : "utf8").replace(/\u0000/g, " ");
  const text = lower.endsWith(".pdf")
    ? raw.replace(/%PDF-[^\n]+/g, "").replace(/[^\p{L}\p{N}\p{P}\p{Zs}\n]+/gu, " ")
    : raw;
  const normalized = text.replace(/[ \t]+/g, " ").trim();
  if (normalized) {
    return normalized;
  }
  return `Binary document (${content.length} bytes) uploaded.`;
}

function sanitizeFilename(value: string): string {
  return basename(value).replace(/[^a-zA-Z0-9._-]/g, "_") || "document.txt";
}

function inferSourceType(sourceName: string): string {
  return sourceName.toLowerCase().endsWith(".pdf") ? "PDF" : "TEXT";
}

function sha256Buffer(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function isReady(job: IngestionJobRecord): boolean {
  return ["PENDING", "QUEUED"].includes(job.status)
    || (job.status === "RETRY" && (!job.nextRetryAt || Date.parse(job.nextRetryAt) <= Date.now()));
}

function truncateError(value: string): string {
  return value.slice(0, 1024);
}
