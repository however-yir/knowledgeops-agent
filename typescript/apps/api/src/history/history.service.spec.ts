import { describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
import { HistoryService } from "./history.service.js";

describe("HistoryService", () => {
  it("lists chat ids and newest-first messages like the Java history contract", () => {
    const service = new HistoryService(new PlatformStore());

    service.appendExchange("public", "chat", "chat-1", "hello", "hi there");

    expect(service.listChatIds("public", "chat", 1, 20)).toMatchObject({
      items: ["chat-1"],
      total: 1,
      page: 1,
      pageSize: 20
    });
    expect(service.listMessages("public", "chat", "chat-1", 1, 50).items).toEqual([
      { role: "assistant", content: "hi there" },
      { role: "user", content: "hello" }
    ]);
  });

  it("derives sessions from messages, clamps pagination, and isolates tenants", () => {
    const store = new PlatformStore();
    const service = new HistoryService(store);
    service.saveSession("public", "chat", "empty");
    service.appendExchange("tenant-a", "chat", "older", "one", "two");
    service.appendExchange("tenant-a", "chat", "latest", "three", "four");
    service.appendExchange("tenant-b", "chat", "private", "secret", "answer");
    const older = store.conversations.filter((item) => item.conversationId === "chat::older");
    older.forEach((item) => { item.createdAt = "2026-01-01T00:00:00.000Z"; });

    expect(service.listChatIds("public", "chat", 1, 20).items).toEqual([]);
    expect(service.listChatIds("tenant-a", "chat", 0, 1)).toMatchObject({
      items: ["latest"],
      total: 2,
      page: 1,
      pageSize: 1
    });
    expect(service.listChatIds("tenant-a", "chat", 2, 1).items).toEqual(["older"]);
    expect(service.listMessages("tenant-a", "chat", "private", 1, 50).items).toEqual([]);
  });

  it("maps Java roles and returns latest N in chronological memory order", () => {
    const store = new PlatformStore();
    const service = new HistoryService(store);
    store.conversations.push(
      { tenantId: "public", conversationId: "chat::chat-1", role: "SYSTEM" as never, content: "system", createdAt: "2026-01-01T00:00:00.000Z" },
      { tenantId: "public", conversationId: "chat::chat-1", role: "USER" as never, content: "first", createdAt: "2026-01-01T00:00:01.000Z" },
      { tenantId: "public", conversationId: "chat::chat-1", role: "TOOL" as never, content: "skip", createdAt: "2026-01-01T00:00:02.000Z" },
      { tenantId: "public", conversationId: "chat::chat-1", role: "ASSISTANT" as never, content: "last", createdAt: "2026-01-01T00:00:03.000Z" }
    );

    expect(service.listMessages("public", "chat", "chat-1", 1, 10).items).toEqual([
      { role: "assistant", content: "last" },
      { role: "", content: "skip" },
      { role: "user", content: "first" },
      { role: "system", content: "system" }
    ]);
    expect(service.latestMessages("public", "chat", "chat-1", 3)).toEqual([
      { role: "user", content: "first" },
      { role: "assistant", content: "last" }
    ]);
    expect(service.latestMessages("public", "chat", "chat-1", 0)).toEqual([]);
  });
});
