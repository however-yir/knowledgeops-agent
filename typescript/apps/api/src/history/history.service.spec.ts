import { describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
import { HistoryService } from "./history.service.js";

describe("HistoryService", () => {
  it("lists chat ids and messages like the Java history contract", () => {
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
});
