import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";

import { Injectable } from "@nestjs/common";
import type { IngestionJob } from "@knowledgeops/shared";

import { newId, nowIso } from "../common/ids.js";
import { env } from "../config/env.js";
import { RetrievalService } from "../ai/retrieval.service.js";
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
    const sourceName = sanitizeFilename(params.sourceName || "document.txt");
    const filePath = await persistUpload(jobId, sourceName, params.content);
    const rawText = extractText(params.content);
    const job: IngestionJobRecord = {
      jobId,
      tenantId: params.tenantId,
      chatId: params.chatId,
      sourceName,
      sourceType: inferSourceType(sourceName),
      filePath,
      idempotencyKey,
      contentHash,
      rawText,
      status: "PENDING",
      attemptCount: 0,
      maxRetries: 3,
      traceId: params.traceId ?? "",
      queueBackend: "in-memory",
      createdAt: nowIso()
    };
    this.store.ingestionJobs.set(`${params.tenantId}:${job.jobId}`, job);
    this.store.idempotencyIndex.set(`${params.tenantId}:${idempotencyKey}`, job.jobId);
    this.store.persist();
    return toPublicJob(job);
  }

  getJob(tenantId: string, jobId: string): IngestionJob | undefined {
    const job = this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
    return job ? toPublicJob(job) : undefined;
  }

  listByChatId(tenantId: string, chatId: string, limit: number): IngestionJob[] {
    return [...this.store.ingestionJobs.entries()]
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && job.chatId === chatId)
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
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && (!jobId || job.jobId === jobId) && ["PENDING", "QUEUED", "RETRY"].includes(job.status));
    const [, job] = candidates[0] ?? [];
    if (!job) {
      return "empty";
    }
    job.status = "RUNNING";
    job.startedAt = job.startedAt ?? nowIso();
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
    } catch (error) {
      job.attemptCount += 1;
      job.errorMessage = error instanceof Error ? error.message : String(error);
      job.status = job.attemptCount < job.maxRetries ? "RETRY" : "FAILED";
      job.finishedAt = nowIso();
    }
    this.store.persist();
    return "processed";
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

function extractText(content: Buffer): string {
  const text = content.toString("utf8").replace(/\u0000/g, "").trim();
  if (text) {
    return text;
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
