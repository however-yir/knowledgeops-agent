import { describe, expect, it } from "vitest";

import { PlatformStore, type IngestionJobRecord } from "../platform/platform.store.js";
import { TenantIngestionJobRepository } from "./ingestion.repository.js";

describe("TenantIngestionJobRepository", () => {
  it("recovers abandoned claims and respects retry exhaustion", async () => {
    const store = new PlatformStore();
    store.ingestionJobs.clear();
    const repository = new TenantIngestionJobRepository(store);
    const retryable = job("retryable", 1, 3);
    const exhausted = job("exhausted", 3, 3);
    store.ingestionJobs.set(`public:${retryable.jobId}`, retryable);
    store.ingestionJobs.set(`public:${exhausted.jobId}`, exhausted);

    await expect(repository.recoverStalled()).resolves.toBe(2);

    expect(retryable.status).toBe("RETRY");
    expect(retryable.nextRetryAt).toBeTruthy();
    expect(exhausted.status).toBe("FAILED");
    expect(exhausted.nextRetryAt).toBeUndefined();
    expect(exhausted.errorMessage).toBe("recovered abandoned ingestion claim");
  });

  it("claims a ready retry once and increments its attempt", async () => {
    const store = new PlatformStore();
    store.ingestionJobs.clear();
    const repository = new TenantIngestionJobRepository(store);
    const record = { ...job("ready", 1, 3), status: "RETRY" as const, nextRetryAt: new Date(0).toISOString() };
    store.ingestionJobs.set(`public:${record.jobId}`, record);

    const claimed = await repository.claim("public", record.jobId);

    expect(claimed).toMatchObject({ status: "RUNNING", attemptCount: 2 });
    await expect(repository.claim("public", record.jobId)).resolves.toBeUndefined();
  });
});

function job(jobId: string, attemptCount: number, maxRetries: number): IngestionJobRecord {
  const stale = new Date(Date.now() - 120_000).toISOString();
  return {
    jobId,
    tenantId: "public",
    chatId: "chat-1",
    sourceName: `${jobId}.txt`,
    sourceType: "TEXT",
    filePath: `/tmp/${jobId}.txt`,
    idempotencyKey: jobId,
    contentHash: jobId,
    rawText: "recoverable content",
    status: "RUNNING",
    attemptCount,
    maxRetries,
    traceId: "trace-1",
    queueBackend: "redis_stream",
    createdAt: stale,
    startedAt: stale,
    updatedAt: stale
  };
}
