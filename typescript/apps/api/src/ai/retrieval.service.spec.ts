import { describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
import { HYBRID_WEIGHT_PRESETS, hybridWeights } from "./hybrid-weights.js";
import { RetrievalService } from "./retrieval.service.js";

describe("RetrievalService", () => {
  it("returns grounded answers with citations for matching chunks", () => {
    const service = new RetrievalService(new PlatformStore());
    service.addDocumentChunks({
      tenantId: "public",
      chatId: "chat-1",
      jobId: "job-1",
      fileName: "handbook.txt",
      sourceType: "TEXT",
      text: "The refund policy allows cancellation within seven days."
    });

    const answer = service.answer("refund cancellation", "public", "chat-1");

    expect(answer.answer).toContain("refund policy");
    expect(answer.citations[0]).toMatchObject({
      source: "handbook.txt",
      title: "handbook.txt",
      chunkId: "job-1:0"
    });
    expect(answer.citations[0]?.snippet).toContain("refund policy");
    expect(answer.evidence[0]).toContain("seven days");
  });

  it("includes graph facts in hybrid retrieval", () => {
    const store = new PlatformStore();
    store.graphFacts.push({
      factId: "fact-1",
      tenantId: "public",
      subject: "Heat safety",
      predicate: "requires",
      object: "shade and water",
      confidence: 0.9,
      metadata: {},
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
    const service = new RetrievalService(store);

    const result = service.hybridRetrieve("heat safety water", "public", "chat-1");

    expect(result.documents[0]?.source).toBe("graph");
    expect(result.documents[0]?.content).toContain("shade and water");
  });

  it("applies configurable per-source weights to the fusion", () => {
    const service = new RetrievalService(new PlatformStore());
    service.addDocumentChunks({
      tenantId: "public",
      chatId: "chat-1",
      jobId: "job-1",
      fileName: "handbook.txt",
      sourceType: "TEXT",
      text: "The refund policy allows cancellation within seven days."
    });

    const baseline = service.hybridRetrieve("refund cancellation", "public", "chat-1");
    const keywordHeavy = service.hybridRetrieve("refund cancellation", "public", "chat-1", undefined, HYBRID_WEIGHT_PRESETS.KEYWORD);
    const baselineKeywordDoc = baseline.documents.find((doc) => doc.source === "keyword");
    const keywordHeavyDoc = keywordHeavy.documents.find((doc) => doc.chunkId === baselineKeywordDoc?.chunkId);

    expect(baselineKeywordDoc).toBeDefined();
    expect(keywordHeavyDoc?.finalScore).toBeCloseTo((baselineKeywordDoc?.finalScore ?? 0) * 2, 6);

    const unitVector = service.hybridRetrieve("refund cancellation", "public", "chat-1", undefined, hybridWeights(1, 0, 0, 0));
    const doubledVector = service.hybridRetrieve("refund cancellation", "public", "chat-1", undefined, hybridWeights(2, 0, 0, 0));
    expect(doubledVector.documents.map((doc) => doc.chunkId)).toEqual(unitVector.documents.map((doc) => doc.chunkId));
    expect(doubledVector.documents.map((doc) => doc.finalScore)).toEqual(unitVector.documents.map((doc) => doc.finalScore));
  });

  it("keeps retrieval results scoped to tenant and chat id", () => {
    const service = new RetrievalService(new PlatformStore());
    service.addDocumentChunks({
      tenantId: "public",
      chatId: "chat-1",
      jobId: "job-1",
      fileName: "public.txt",
      sourceType: "TEXT",
      text: "The public tenant policy mentions shade."
    });
    service.addDocumentChunks({
      tenantId: "acme",
      chatId: "chat-1",
      jobId: "job-2",
      fileName: "acme.txt",
      sourceType: "TEXT",
      text: "The acme tenant policy mentions hydration."
    });
    service.addDocumentChunks({
      tenantId: "public",
      chatId: "chat-2",
      jobId: "job-3",
      fileName: "other-chat.txt",
      sourceType: "TEXT",
      text: "The other chat policy mentions hydration."
    });

    expect(service.retrieve("hydration", "public", "chat-1")).toHaveLength(0);
    expect(service.retrieve("hydration", "acme", "chat-1")[0]?.fileName).toBe("acme.txt");
    expect(service.retrieve("hydration", "public", "chat-2")[0]?.fileName).toBe("other-chat.txt");
  });
});
