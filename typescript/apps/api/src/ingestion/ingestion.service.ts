import { Injectable } from "@nestjs/common";
import type { IngestionJob } from "@knowledgeops/shared";

import { newId, nowIso } from "../common/ids.js";
import { PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class IngestionService {
  constructor(private readonly store: PlatformStore) {}

  createJob(tenantId: string, chatId: string, sourceName = "document.pdf", traceId = ""): IngestionJob {
    const job: IngestionJob = {
      jobId: newId("job"),
      chatId,
      sourceName,
      status: "QUEUED",
      attemptCount: 0,
      maxRetries: 3,
      traceId,
      queueBackend: "in-memory",
      createdAt: nowIso()
    };
    this.store.ingestionJobs.set(`${tenantId}:${job.jobId}`, job);
    return job;
  }

  getJob(tenantId: string, jobId: string): IngestionJob | undefined {
    return this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
  }

  listByChatId(tenantId: string, chatId: string, limit: number): IngestionJob[] {
    return [...this.store.ingestionJobs.entries()]
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && job.chatId === chatId)
      .map(([, job]) => job)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, Math.max(1, Math.min(limit, 100)));
  }

  processOne(tenantId: string, jobId?: string): string {
    const candidates = [...this.store.ingestionJobs.entries()]
      .filter(([key, job]) => key.startsWith(`${tenantId}:`) && (!jobId || job.jobId === jobId) && job.status === "QUEUED");
    const [, job] = candidates[0] ?? [];
    if (!job) {
      return "empty";
    }
    job.status = "COMPLETED";
    job.startedAt = job.startedAt ?? nowIso();
    job.finishedAt = nowIso();
    return "processed";
  }
}
