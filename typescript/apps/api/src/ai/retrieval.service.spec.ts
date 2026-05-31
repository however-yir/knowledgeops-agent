import { describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
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
    expect(answer.citations).toEqual(["source=handbook.txt, chunk=0"]);
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
});
