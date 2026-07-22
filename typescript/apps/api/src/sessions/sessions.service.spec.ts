import { describe, expect, it } from "vitest";
import type { SessionBranch, SessionMessage } from "@knowledgeops/shared";

import { PlatformStore } from "../platform/platform.store.js";
import { SessionsService } from "./sessions.service.js";

describe("SessionsService", () => {
  it("applies Java upsert defaults without exposing the internal tenant id", () => {
    const store = new PlatformStore();
    const service = new SessionsService(store);

    const saved = service.upsert("tenant-a", " session-1 ", {
      title: " ",
      branches: [branch("main")]
    });

    expect(saved).toMatchObject({
      id: "session-1",
      title: "新会话",
      workspaceId: "default",
      modelProfile: "balanced",
      streaming: true,
      pinned: false,
      archived: false,
      activeBranchId: "main"
    });
    expect(saved).not.toHaveProperty("tenantId");
    expect([...store.sessions.values()][0]?.tenantId).toBe("tenant-a");
  });

  it("filters, paginates, and sorts like the Java session query", () => {
    const store = new PlatformStore();
    const service = new SessionsService(store);
    service.upsert("tenant-a", "older", { title: "Heat notes", workspaceId: "ops" });
    service.upsert("tenant-a", "pinned", { title: "Heat plan", workspaceId: "ops", pinned: true });
    service.upsert("tenant-a", "archived", { title: "Heat archive", workspaceId: "ops", archived: true });
    service.upsert("tenant-a", "other", { title: "Heat other", workspaceId: "other" });
    const sessions = new Map([...store.sessions.values()].map((session) => [session.id, session]));
    sessions.get("older")!.updatedAt = 1;
    sessions.get("pinned")!.updatedAt = 2;
    sessions.get("archived")!.updatedAt = 3;
    sessions.get("other")!.updatedAt = 4;

    expect(service.list("tenant-a", 1, 1, false, " heat ", "ops")).toMatchObject({
      items: [{ id: "pinned" }],
      total: 2,
      page: 1,
      pageSize: 1
    });
    expect(service.list("tenant-a", 1, 20, true, undefined, "all").items.map((item) => item.id)).toEqual([
      "pinned", "other", "archived", "older"
    ]);
  });

  it("compares unique fingerprints and preserves Java preview ordering", () => {
    const service = new SessionsService(new PlatformStore());
    service.upsert("tenant-a", "session-1", {
      branches: [
        branch("source", [message("s1", "user", "same"), message("s2", "user", "same"), message("s3", "assistant", "source only")]),
        branch("target", [message("t1", "user", "same"), message("t2", "assistant", "target only")])
      ]
    });

    expect(service.compare("tenant-a", "session-1", "source", "target")).toEqual({
      sourceBranchId: "source",
      targetBranchId: "target",
      sourceMessageCount: 3,
      targetMessageCount: 2,
      commonMessageCount: 1,
      sourceOnlyCount: 1,
      targetOnlyCount: 1,
      sourceOnlyPreview: ["source only"],
      targetOnlyPreview: ["target only"]
    });
  });

  it("copies merged messages and repairs source id collisions", () => {
    const service = new SessionsService(new PlatformStore());
    const sourceMessage = message("duplicate", "assistant", "new content");
    service.upsert("tenant-a", "session-1", {
      branches: [
        branch("source", [sourceMessage]),
        branch("target", [message("duplicate", "user", "existing")])
      ]
    });

    const result = service.merge("tenant-a", "session-1", "source", "target");

    expect(result.mergedBranch.id).toMatch(/^branch-merge-/);
    expect(result.mergedBranch.title).toBe("target · merge");
    expect(result.mergedBranch.messages.map((item) => item.id)).toEqual(["duplicate", "duplicate-m1"]);
    expect(result.session.activeBranchId).toBe(result.mergedBranch.id);
    expect(result.session.branches[0]?.id).toBe(result.mergedBranch.id);
    expect(sourceMessage.id).toBe("duplicate");
  });
});

function branch(id: string, messages: SessionMessage[] = []): SessionBranch {
  return {
    id,
    title: id,
    parentBranchId: null,
    parentMessageId: null,
    updatedAt: 1,
    messages,
    traceSteps: []
  };
}

function message(id: string, role: SessionMessage["role"], content: string): SessionMessage {
  return { id, role, content, createdAt: 1 };
}
