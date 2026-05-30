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
});
