import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { PlatformStore } from "../platform/platform.store.js";
import { AnswerFeedbackService } from "./answer-feedback.service.js";

const tempDirs: string[] = [];
const typescriptRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");

afterEach(() => {
  for (const path of tempDirs.splice(0)) {
    rmSync(path, { recursive: true, force: true });
  }
});

describe("AnswerFeedbackService", () => {
  it("validates the Java required fields and rating range", () => {
    const service = new AnswerFeedbackService(new PlatformStore());
    const disabled = { enabled: false, datasetPath: "unused" };

    expect(() => service.submit("public", undefined, disabled)).toThrow("feedback payload is required");
    expect(() => service.submit("public", { rating: 5, answer: "answer" }, disabled)).toThrow("chatId is required");
    expect(() => service.submit("public", { chatId: "chat", rating: 0, answer: "answer" }, disabled)).toThrow("rating must be between 1 and 5");
    expect(() => service.submit("public", { chatId: "chat", rating: 6, answer: "answer" }, disabled)).toThrow("rating must be between 1 and 5");
    expect(() => service.submit("public", { chatId: "chat", rating: 5, answer: " " }, disabled)).toThrow("answer is required");
  });

  it("persists normalized tenant feedback and truncates comments", () => {
    const store = new PlatformStore();
    const service = new AnswerFeedbackService(store);

    service.submit(" ", {
      chatId: " chat-1 ",
      sessionId: "session-1",
      branchId: "main",
      messageId: "message-1",
      rating: 5,
      comment: `  ${"x".repeat(1100)}  `,
      question: "question",
      answer: "answer"
    }, { enabled: false, datasetPath: "unused" });

    expect(store.feedback).toHaveLength(1);
    expect(store.feedback[0]).toMatchObject({
      tenantId: "public",
      chatId: " chat-1 ",
      sessionId: "session-1",
      branchId: "main",
      messageId: "message-1",
      rating: 5,
      question: "question",
      answer: "answer"
    });
    expect(String(store.feedback[0]?.comment)).toHaveLength(1024);
  });

  it("appends Java-compatible evaluation JSONL when configured", () => {
    const root = mkdtempSync(join(typescriptRoot, ".feedback-test-"));
    tempDirs.push(root);
    const datasetPath = join(root, "nested", "feedback.jsonl");
    const service = new AnswerFeedbackService(new PlatformStore());

    service.submit("tenant-a", {
      chatId: "chat-1",
      rating: 1,
      comment: "incorrect citation",
      question: "What changed?",
      answer: "An inaccurate answer"
    }, { enabled: true, datasetPath });

    const item = JSON.parse(readFileSync(datasetPath, "utf8").trim()) as Record<string, unknown>;
    expect(item).toMatchObject({
      category: "user_feedback",
      tenant_id: "tenant-a",
      chatId: "chat-1",
      question: "What changed?",
      answer: "An inaccurate answer",
      rating: 1,
      comment: "incorrect citation",
      expected_keywords: ["改进", "更准确"],
      forbidden_keywords: ["incorrect", "citation", "an", "inaccurate", "answer"]
    });
    expect(item.id).toMatch(/^feedback_\d{4}-\d{2}-\d{2}_\d+$/);
  });
});
