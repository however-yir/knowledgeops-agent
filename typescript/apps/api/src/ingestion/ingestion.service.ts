import { createHash } from "node:crypto";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";

import { Inject, Injectable, Optional } from "@nestjs/common";
import type { IngestionJob } from "@knowledgeops/shared";

import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { IngestionJobRecord, PlatformStore } from "../platform/platform.store.js";
import { IngestionQueueService } from "./ingestion.queue.js";
import { INGESTION_JOB_REPOSITORY, IngestionJobRepository, TenantIngestionJobRepository } from "./ingestion.repository.js";
import { ParsedDocument, parsePdf } from "./pdf.parser.js";

@Injectable()
export class IngestionService {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    @Optional() private readonly queue?: IngestionQueueService,
    @Optional() @Inject(INGESTION_JOB_REPOSITORY) private readonly repository?: IngestionJobRepository
  ) {}

  async createJob(params: {
    tenantId: string;
    chatId: string;
    sourceName?: string;
    content: Buffer;
    idempotencyKey?: string;
    traceId?: string;
  }): Promise<IngestionJob> {
    const tenantId = normalizeTenant(params.tenantId);
    const chatId = params.chatId?.trim();
    if (!chatId) throw new Error("chatId is required");
    if (!params.content.length) throw new Error("file is required");
    const sourceName = sanitizeFilename(params.sourceName || "document.txt");
    const sourceType = inferSourceType(sourceName);
    scanFile(sourceName, params.content);
    const contentHash = sha256Buffer(params.content);
    const providedKey = params.idempotencyKey?.trim();
    if (providedKey && providedKey.length > 256) throw new Error("idempotency key is too long");
    const idempotencyKey = providedKey
      ? `client:${providedKey}`
      : `auto:${sha256Text(`${tenantId}|${chatId}|${contentHash}`)}`;
    const repository = this.jobRepository();
    const existing = await repository.findByIdempotency(tenantId, idempotencyKey);
    if (existing) return toPublicJob(existing);
    const parsed = await parseUploadedDocument(sourceType, params.content);

    const jobId = newId("job");
    const now = nowIso();
    const filePath = await persistUpload(jobId, sourceName, params.content);
    const job: IngestionJobRecord = {
      jobId,
      tenantId,
      chatId,
      sourceName,
      sourceType,
      filePath,
      idempotencyKey,
      contentHash,
      rawText: parsed.text,
      pages: parsed.pages,
      status: "PENDING",
      attemptCount: 0,
      maxRetries: env.APP_INGESTION_MAX_RETRIES,
      traceId: params.traceId ?? "",
      queueBackend: env.APP_INGESTION_QUEUE_BACKEND,
      createdAt: now,
      updatedAt: now
    };
    const persisted = await repository.insertIfAbsent(job);
    if (persisted.jobId !== job.jobId) await unlink(filePath).catch(() => undefined);
    this.store.incrementMetric("ingestion_jobs_submitted_total", { source: persisted.sourceType, tenant: tenantId });
    this.store.persist();
    if (persisted.jobId === job.jobId) {
      try {
        await this.queue?.enqueue(persisted);
      } catch (error) {
        persisted.status = "RETRY";
        persisted.errorMessage = `failed to enqueue ${env.APP_INGESTION_QUEUE_BACKEND} job: ${truncateError(error instanceof Error ? error.message : String(error))}`;
        persisted.nextRetryAt = new Date(Date.now() + env.APP_INGESTION_BASE_DELAY_SECONDS * 1000).toISOString();
        persisted.updatedAt = nowIso();
        await repository.save(persisted);
      }
    }
    return toPublicJob(persisted);
  }

  getJob(tenantId: string, jobId: string): IngestionJob | undefined {
    const job = this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
    return job ? toPublicJob(job) : undefined;
  }

  listByChatId(tenantId: string, chatId: string, limit: number): IngestionJob[] {
    return [...this.store.ingestionJobs.values()]
      .filter((job) => job.tenantId === tenantId && (!chatId || job.chatId === chatId))
      .map(toPublicJob)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, Math.max(1, Math.min(limit, 100)));
  }

  latestFileForChat(tenantId: string, chatId: string): { filePath: string; sourceName: string } | undefined {
    const latest = [...this.store.ingestionJobs.values()]
      .filter((job) => job.tenantId === tenantId && job.chatId === chatId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
    return latest ? { filePath: latest.filePath, sourceName: latest.sourceName } : undefined;
  }

  async processOne(tenantId: string, jobId?: string): Promise<string> {
    const repository = this.jobRepository();
    const job = await repository.claim(tenantId, jobId);
    if (!job) return "empty";
    const leaseToken = job.leaseToken;
    if (!leaseToken) throw new Error(`ingestion job ${job.jobId} was claimed without a lease`);
    const leaseHeartbeat = setInterval(() => {
      void repository.renewLease(job.tenantId, job.jobId, leaseToken);
    }, Math.max(500, Math.floor(env.APP_INGESTION_CLAIM_IDLE_MS / 3)));
    leaseHeartbeat.unref?.();
    try {
      const parsed = await this.loadDocument(job);
      await this.retrievalService.addDocumentChunks({
        tenantId: job.tenantId,
        chatId: job.chatId,
        jobId: job.jobId,
        fileName: job.sourceName,
        sourceType: job.sourceType,
        text: parsed.text,
        pages: parsed.pages
      });
      job.status = "SUCCEEDED";
      job.finishedAt = nowIso();
      job.errorMessage = undefined;
      job.nextRetryAt = undefined;
      this.store.incrementMetric("ingestion_jobs_finished_total", { status: "succeeded", tenant: tenantId });
    } catch (error) {
      job.errorMessage = truncateError(error instanceof Error ? error.message : String(error));
      job.status = job.attemptCount < job.maxRetries ? "RETRY" : "FAILED";
      job.nextRetryAt = job.status === "RETRY"
        ? new Date(Date.now() + env.APP_INGESTION_BASE_DELAY_SECONDS * Math.max(1, job.attemptCount) * 1000).toISOString()
        : undefined;
      job.finishedAt = nowIso();
      this.store.incrementMetric("ingestion_jobs_finished_total", { status: job.status.toLowerCase(), tenant: tenantId });
    } finally {
      clearInterval(leaseHeartbeat);
    }
    job.updatedAt = nowIso();
    if (!await repository.save(job, leaseToken)) return "lost-lease";
    if (job.status === "FAILED") {
      await this.queue?.publishDlq(job, job.errorMessage ?? "max retries exceeded").catch(() => undefined);
    }
    return "processed";
  }

  async processReadyBatch(limit = env.APP_INGESTION_WORKER_CONCURRENCY): Promise<number> {
    const batchSize = Math.max(1, limit);
    if (this.queue?.enabled()) {
      await this.jobRepository().recoverStalled(batchSize);
      await this.enqueueReadyRetries(undefined, batchSize);
      const messages = await this.queue.next(batchSize);
      let processed = 0;
      for (const message of messages) {
        const outcome = await this.processOne(message.tenantId, message.jobId);
        // Only ack deliveries whose job reached a terminal status; transient
        // outcomes (RETRY/PENDING, lease lost, in flight elsewhere) stay
        // pending so the idle-claimer redelivers them instead of silently
        // losing the message (mirror of the Java f112ce7 loopConsume fix).
        const job = this.getJob(message.tenantId, message.jobId);
        const terminal = job?.status === "SUCCEEDED" || job?.status === "FAILED";
        if (terminal || !job) {
          await this.queue.ack(message.streamId);
        }
        if (outcome === "processed") processed += 1;
      }
      return processed;
    }
    const candidates = await this.jobRepository().findReady(undefined, batchSize);
    let processed = 0;
    for (const job of candidates) {
      if (await this.processOne(job.tenantId, job.jobId) === "processed") processed += 1;
    }
    return processed;
  }

  async enqueueReadyRetries(tenantId?: string, limit = 50): Promise<number> {
    if (!this.queue?.enabled()) return 0;
    const ready = (await this.jobRepository().findReady(tenantId, Math.max(1, limit)))
      .filter((job) => job.status === "RETRY");
    let enqueued = 0;
    for (const job of ready) {
      const reserved = await this.jobRepository().reserveEnqueue(job);
      if (!reserved) continue;
      try {
        await this.queue.enqueue(reserved);
        if (await this.jobRepository().completeEnqueue(reserved)) enqueued += 1;
      } catch (error) {
        await this.jobRepository().releaseEnqueue(
          reserved,
          `failed to requeue job: ${truncateError(error instanceof Error ? error.message : String(error))}`
        );
      }
    }
    return enqueued;
  }

  private jobRepository(): IngestionJobRepository {
    return this.repository ?? new TenantIngestionJobRepository(this.store);
  }

  private async loadDocument(job: IngestionJobRecord): Promise<ParsedDocument> {
    if (job.rawText?.trim()) return { text: job.rawText, pages: job.pages };
    const content = await readFile(job.filePath);
    return parseUploadedDocument(job.sourceType, content);
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
  await writeFile(filePath, content, { flag: "wx" });
  return filePath;
}

function scanFile(sourceName: string, content: Buffer): void {
  const lower = sourceName.toLowerCase();
  if (content.length > env.APP_INGESTION_MAX_FILE_BYTES) throw new Error(`file exceeds max size ${env.APP_INGESTION_MAX_FILE_BYTES} bytes`);
  const mimeType = inferMimeType(lower);
  const allowed = new Set(env.APP_ALLOWED_UPLOAD_MIME_TYPES.split(",").map((item) => item.trim()).filter(Boolean));
  if (!allowed.has(mimeType) && !allowed.has("application/octet-stream")) throw new Error(`file mime type ${mimeType} is not allowed`);
  const head = content.subarray(0, 8192).toString("latin1");
  if (head.includes("EICAR-STANDARD-ANTIVIRUS-TEST-FILE")) throw new Error("file blocked by malware signature");
  if (lower.endsWith(".pdf") && !head.startsWith("%PDF-")) throw new Error("invalid pdf header");
}

async function parseUploadedDocument(sourceType: string, content: Buffer): Promise<ParsedDocument> {
  if (sourceType === "PDF") return parsePdf(content);
  const text = content.toString("utf8").replace(/\u0000/g, "").replace(/\r\n/g, "\n").trim();
  return { text: text || `Binary document (${content.length} bytes) uploaded.` };
}

function sanitizeFilename(value: string): string {
  return basename(value).replace(/[^a-zA-Z0-9._-]/g, "_") || "document.txt";
}

function inferSourceType(sourceName: string): string {
  return sourceName.toLowerCase().endsWith(".pdf") ? "PDF" : "TEXT";
}

function inferMimeType(sourceName: string): string {
  if (sourceName.endsWith(".pdf")) return "application/pdf";
  if (sourceName.endsWith(".md") || sourceName.endsWith(".markdown")) return "text/markdown";
  if (sourceName.endsWith(".txt") || sourceName.endsWith(".text")) return "text/plain";
  return "application/octet-stream";
}

function sha256Buffer(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function truncateError(value: string): string {
  return value.slice(0, 1024);
}
