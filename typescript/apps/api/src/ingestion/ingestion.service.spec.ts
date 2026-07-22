import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import type { IngestionQueueService } from "./ingestion.queue.js";
import { TenantIngestionJobRepository } from "./ingestion.repository.js";
import { IngestionService } from "./ingestion.service.js";

describe("IngestionService", () => {
  it("ingests text once by idempotency key and makes chunks retrievable", async () => {
    const store = new PlatformStore();
    const retrieval = new RetrievalService(store);
    const ingestion = new IngestionService(store, retrieval);

    const first = await ingestion.createJob({
      tenantId: "public",
      chatId: "chat-1",
      sourceName: "policy.txt",
      content: Buffer.from("Heat safety requires shade, water, and rest breaks."),
      idempotencyKey: "same-upload"
    });
    const second = await ingestion.createJob({
      tenantId: "public",
      chatId: "chat-1",
      sourceName: "policy.txt",
      content: Buffer.from("Heat safety requires shade, water, and rest breaks."),
      idempotencyKey: "same-upload"
    });

    expect(second.jobId).toBe(first.jobId);
    await expect(ingestion.processOne("public", first.jobId)).resolves.toBe("processed");
    expect(retrieval.retrieve("shade water", "public", "chat-1")).toHaveLength(1);
  });

  it("blocks known malware signatures before creating a job", async () => {
    const ingestion = new IngestionService(new PlatformStore(), new RetrievalService(new PlatformStore()));

    await expect(ingestion.createJob({
      tenantId: "public",
      chatId: "chat-1",
      sourceName: "eicar.txt",
      content: Buffer.from("X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")
    })).rejects.toThrow("file blocked by malware signature");
  });

  it("rejects PDF uploads with invalid headers", async () => {
    const store = new PlatformStore();
    const ingestion = new IngestionService(store, new RetrievalService(store));

    await expect(ingestion.createJob({
      tenantId: "public",
      chatId: "chat-1",
      sourceName: "not-a-pdf.pdf",
      content: Buffer.from("plain text")
    })).rejects.toThrow("invalid pdf header");
  });

  it("republishes ready retries before reading an external queue", async () => {
    const store = new PlatformStore();
    store.ingestionJobs.clear();
    const enqueued: string[] = [];
    const queue = {
      enabled: () => true,
      enqueue: async (job: { jobId: string }) => { enqueued.push(job.jobId); },
      next: async () => [],
      ack: async () => undefined,
      publishDlq: async () => undefined
    } as unknown as IngestionQueueService;
    const repository = new TenantIngestionJobRepository(store);
    const retry = {
      jobId: "job-retry",
      tenantId: "public",
      chatId: "chat-1",
      sourceName: "retry.txt",
      sourceType: "TEXT",
      filePath: "/tmp/retry.txt",
      idempotencyKey: "retry",
      contentHash: "retry",
      rawText: "retry content",
      status: "RETRY" as const,
      attemptCount: 1,
      maxRetries: 3,
      traceId: "trace-1",
      queueBackend: "redis_stream",
      nextRetryAt: new Date(0).toISOString(),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    store.ingestionJobs.set(`public:${retry.jobId}`, retry);
    const ingestion = new IngestionService(store, new RetrievalService(store), queue, repository);

    await expect(ingestion.processReadyBatch()).resolves.toBe(0);

    expect(enqueued).toEqual(["job-retry"]);
    expect(retry.status).toBe("PENDING");
    expect(retry.nextRetryAt).toBeUndefined();
  });
});
