import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { PlatformStore } from "../platform/platform.store.js";
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
    expect(ingestion.processOne("public", first.jobId)).toBe("processed");
    expect(retrieval.retrieve("shade water", "public", "chat-1")).toHaveLength(1);
  });
});
