import { Injectable } from "@nestjs/common";

import { newId, nowIso } from "../common/ids.js";
import { env } from "../config/env.js";
import { IngestionJobRecord, PlatformStore } from "../platform/platform.store.js";

export const INGESTION_JOB_REPOSITORY = Symbol("INGESTION_JOB_REPOSITORY");

export interface IngestionJobRepository {
  findByIdempotency(tenantId: string, idempotencyKey: string): Promise<IngestionJobRecord | undefined>;
  insertIfAbsent(job: IngestionJobRecord): Promise<IngestionJobRecord>;
  get(tenantId: string, jobId: string): Promise<IngestionJobRecord | undefined>;
  listByChat(tenantId: string, chatId: string, limit: number): Promise<IngestionJobRecord[]>;
  claim(tenantId: string, jobId?: string): Promise<IngestionJobRecord | undefined>;
  renewLease(tenantId: string, jobId: string, leaseToken: string): Promise<boolean>;
  save(job: IngestionJobRecord, leaseToken?: string): Promise<boolean>;
  reserveEnqueue(job: IngestionJobRecord): Promise<IngestionJobRecord | undefined>;
  completeEnqueue(job: IngestionJobRecord): Promise<boolean>;
  releaseEnqueue(job: IngestionJobRecord, errorMessage: string): Promise<boolean>;
  findReady(tenantId?: string, limit?: number): Promise<IngestionJobRecord[]>;
  recoverStalled(limit?: number): Promise<number>;
}

@Injectable()
export class TenantIngestionJobRepository implements IngestionJobRepository {
  private readonly reservations = new Map<string, Promise<IngestionJobRecord>>();

  constructor(private readonly store: PlatformStore) {}

  async findByIdempotency(tenantId: string, idempotencyKey: string): Promise<IngestionJobRecord | undefined> {
    const jobId = this.store.idempotencyIndex.get(`${tenantId}:${idempotencyKey}`);
    return jobId ? this.store.ingestionJobs.get(`${tenantId}:${jobId}`) : undefined;
  }

  async insertIfAbsent(job: IngestionJobRecord): Promise<IngestionJobRecord> {
    const key = `${job.tenantId}:${job.idempotencyKey}`;
    const existing = await this.findByIdempotency(job.tenantId, job.idempotencyKey);
    if (existing) return existing;
    const pending = this.reservations.get(key);
    if (pending) return pending;
    const insertion = Promise.resolve().then(async () => {
      const concurrent = await this.findByIdempotency(job.tenantId, job.idempotencyKey);
      if (concurrent) return concurrent;
      this.store.ingestionJobs.set(`${job.tenantId}:${job.jobId}`, job);
      this.store.idempotencyIndex.set(key, job.jobId);
      this.store.persist();
      return job;
    });
    this.reservations.set(key, insertion);
    try {
      return await insertion;
    } finally {
      this.reservations.delete(key);
    }
  }

  async get(tenantId: string, jobId: string): Promise<IngestionJobRecord | undefined> {
    return this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
  }

  async listByChat(tenantId: string, chatId: string, limit: number): Promise<IngestionJobRecord[]> {
    return [...this.store.ingestionJobs.values()]
      .filter((job) => job.tenantId === tenantId && (!chatId || job.chatId === chatId))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, Math.max(1, Math.min(limit, 100)));
  }

  async claim(tenantId: string, jobId?: string): Promise<IngestionJobRecord | undefined> {
    const job = [...this.store.ingestionJobs.values()]
      .filter((candidate) => candidate.tenantId === tenantId && (!jobId || candidate.jobId === jobId) && isReady(candidate))
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))[0];
    if (!job) return undefined;
    const now = nowIso();
    job.status = "RUNNING";
    job.startedAt = now;
    job.attemptCount += 1;
    job.errorMessage = undefined;
    job.leaseToken = newId("lease");
    job.leaseExpiresAt = new Date(Date.now() + env.APP_INGESTION_CLAIM_IDLE_MS).toISOString();
    job.updatedAt = now;
    this.store.persist();
    return cloneJob(job);
  }

  async renewLease(tenantId: string, jobId: string, leaseToken: string): Promise<boolean> {
    const job = this.store.ingestionJobs.get(`${tenantId}:${jobId}`);
    if (!job || job.status !== "RUNNING" || job.leaseToken !== leaseToken) return false;
    job.leaseExpiresAt = new Date(Date.now() + env.APP_INGESTION_CLAIM_IDLE_MS).toISOString();
    job.updatedAt = nowIso();
    this.store.persist();
    return true;
  }

  async save(job: IngestionJobRecord, leaseToken?: string): Promise<boolean> {
    const key = `${job.tenantId}:${job.jobId}`;
    const current = this.store.ingestionJobs.get(key);
    if (leaseToken && current?.leaseToken !== leaseToken) return false;
    const persisted = cloneJob(job);
    if (persisted.status !== "RUNNING") {
      persisted.leaseToken = undefined;
      persisted.leaseExpiresAt = undefined;
    }
    this.store.ingestionJobs.set(key, persisted);
    this.store.idempotencyIndex.set(`${persisted.tenantId}:${persisted.idempotencyKey}`, persisted.jobId);
    this.store.persist();
    return true;
  }

  async reserveEnqueue(job: IngestionJobRecord): Promise<IngestionJobRecord | undefined> {
    const current = this.store.ingestionJobs.get(`${job.tenantId}:${job.jobId}`);
    if (!current || current.status !== "RETRY" || current.updatedAt !== job.updatedAt || !isReady(current)) return undefined;
    current.status = "QUEUED";
    current.nextRetryAt = undefined;
    current.leaseExpiresAt = new Date(Date.now() + env.APP_INGESTION_CLAIM_IDLE_MS).toISOString();
    current.updatedAt = nowIso();
    this.store.persist();
    return cloneJob(current);
  }

  async completeEnqueue(job: IngestionJobRecord): Promise<boolean> {
    const current = this.store.ingestionJobs.get(`${job.tenantId}:${job.jobId}`);
    if (!current || current.status !== "QUEUED" || current.updatedAt !== job.updatedAt) return false;
    current.status = "PENDING";
    current.leaseExpiresAt = undefined;
    current.updatedAt = nowIso();
    this.store.persist();
    return true;
  }

  async releaseEnqueue(job: IngestionJobRecord, errorMessage: string): Promise<boolean> {
    const current = this.store.ingestionJobs.get(`${job.tenantId}:${job.jobId}`);
    if (!current || current.status !== "QUEUED" || current.updatedAt !== job.updatedAt) return false;
    current.status = "RETRY";
    current.errorMessage = errorMessage;
    current.leaseExpiresAt = undefined;
    current.nextRetryAt = new Date(Date.now() + env.APP_INGESTION_BASE_DELAY_SECONDS * 1000).toISOString();
    current.updatedAt = nowIso();
    this.store.persist();
    return true;
  }

  async findReady(tenantId?: string, limit = 50): Promise<IngestionJobRecord[]> {
    return [...this.store.ingestionJobs.values()]
      .filter((job) => (!tenantId || job.tenantId === tenantId) && isReady(job))
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .slice(0, Math.max(1, limit));
  }

  async recoverStalled(limit = 50): Promise<number> {
    const staleBefore = Date.now() - env.APP_INGESTION_CLAIM_IDLE_MS;
    const stale = [...this.store.ingestionJobs.values()]
      .filter((job) => ["RUNNING", "QUEUED"].includes(job.status) && leaseExpired(job, staleBefore))
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .slice(0, Math.max(1, limit));
    for (const job of stale) {
      const now = nowIso();
      const abandonedEnqueue = job.status === "QUEUED";
      job.status = abandonedEnqueue || job.attemptCount < job.maxRetries ? "RETRY" : "FAILED";
      job.errorMessage = abandonedEnqueue ? "recovered abandoned enqueue reservation" : "recovered abandoned ingestion claim";
      job.nextRetryAt = job.status === "RETRY" ? now : undefined;
      job.finishedAt = now;
      job.updatedAt = now;
      await this.save(job);
    }
    return stale.length;
  }
}

function leaseExpired(job: IngestionJobRecord, staleBefore: number): boolean {
  if (job.leaseExpiresAt) return Date.parse(job.leaseExpiresAt) <= Date.now();
  return Date.parse(job.updatedAt ?? job.startedAt ?? job.createdAt) <= staleBefore;
}

function cloneJob(job: IngestionJobRecord): IngestionJobRecord {
  return {
    ...job,
    pages: job.pages?.map((page) => ({ ...page }))
  };
}

function isReady(job: IngestionJobRecord): boolean {
  return ["PENDING", "QUEUED"].includes(job.status)
    || (job.status === "RETRY" && (!job.nextRetryAt || Date.parse(job.nextRetryAt) <= Date.now()));
}
