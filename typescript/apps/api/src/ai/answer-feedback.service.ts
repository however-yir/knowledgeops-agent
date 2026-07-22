import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { BadRequestException, Injectable, InternalServerErrorException } from "@nestjs/common";

import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { PlatformStore } from "../platform/platform.store.js";

export interface AnswerFeedbackPayload {
  chatId?: string;
  sessionId?: string;
  branchId?: string;
  messageId?: string;
  rating?: number;
  comment?: string;
  question?: string;
  answer?: string;
}

interface FeedbackOptions {
  enabled: boolean;
  datasetPath: string;
}

@Injectable()
export class AnswerFeedbackService {
  constructor(private readonly store: PlatformStore) {}

  submit(tenantId: string, payload: AnswerFeedbackPayload | null | undefined, options: FeedbackOptions = defaultOptions()): void {
    if (!payload) {
      throw new BadRequestException("feedback payload is required");
    }
    if (!hasText(payload.chatId)) {
      throw new BadRequestException("chatId is required");
    }
    if (!Number.isInteger(payload.rating) || Number(payload.rating) < 1 || Number(payload.rating) > 5) {
      throw new BadRequestException("rating must be between 1 and 5");
    }
    if (!hasText(payload.answer)) {
      throw new BadRequestException("answer is required");
    }

    const createdAt = new Date();
    const feedback = {
      tenantId: normalizeTenant(tenantId),
      chatId: payload.chatId as string,
      sessionId: payload.sessionId,
      branchId: payload.branchId,
      messageId: payload.messageId,
      rating: payload.rating as number,
      comment: trimToLength(payload.comment, 1024),
      question: payload.question,
      answer: payload.answer as string,
      createdAt: createdAt.toISOString()
    };
    this.store.feedback.push(feedback);
    this.store.persist();

    if (options.enabled) {
      appendFeedbackDataset(options.datasetPath, feedback, createdAt);
    }
  }
}

function appendFeedbackDataset(
  datasetPath: string,
  feedback: {
    tenantId: string;
    chatId: string;
    rating: number;
    comment: string;
    question?: string;
    answer: string;
  },
  createdAt: Date
): void {
  const keywords = extractKeywords(`${defaultText(feedback.comment, "")} ${defaultText(feedback.answer, "")}`);
  const item: Record<string, unknown> = {
    id: `feedback_${localDate(createdAt)}_${process.hrtime.bigint()}`,
    category: "user_feedback",
    tenant_id: feedback.tenantId,
    chatId: feedback.chatId,
    question: defaultText(feedback.question, "用户反馈问题"),
    answer: trimToLength(feedback.answer, 1500),
    rating: feedback.rating,
    comment: defaultText(feedback.comment, ""),
    created_at: localDateTime(createdAt)
  };
  if (feedback.rating >= 4) {
    item.expected_keywords = keywords;
    item.forbidden_keywords = ["不知道", "无法回答", "胡编"];
  } else if (feedback.rating <= 2) {
    item.expected_keywords = ["改进", "更准确"];
    item.forbidden_keywords = keywords;
  } else {
    item.expected_keywords = keywords;
    item.forbidden_keywords = [];
  }

  try {
    mkdirSync(dirname(datasetPath), { recursive: true });
    appendFileSync(datasetPath, `${JSON.stringify(item)}\n`, "utf8");
  } catch (error) {
    throw new InternalServerErrorException("failed to append feedback dataset", { cause: error });
  }
}

export function extractKeywords(text: string): string[] {
  if (!hasText(text)) {
    return [];
  }
  const stopWords = new Set(["这个", "那个", "然后", "但是", "我们", "你们", "他们", "以及", "因为"]);
  const values = new Set<string>();
  for (const token of text.toLocaleLowerCase().split(/[^\p{Script=Han}\p{L}\p{N}]+/u)) {
    if (!hasText(token) || token.length < 2 || stopWords.has(token)) {
      continue;
    }
    values.add(token);
    if (values.size >= 6) {
      break;
    }
  }
  return [...values];
}

function defaultOptions(): FeedbackOptions {
  return {
    enabled: env.APP_FEEDBACK_ENABLED,
    datasetPath: env.APP_FEEDBACK_DATASET_PATH
  };
}

function trimToLength(value: unknown, maxLength: number): string {
  if (!hasText(value)) {
    return "";
  }
  const normalized = String(value).trim();
  return normalized.length <= maxLength ? normalized : normalized.slice(0, maxLength);
}

function defaultText(value: unknown, fallback: string): string {
  return hasText(value) ? String(value) : fallback;
}

function hasText(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function localDate(value: Date): string {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function localDateTime(value: Date): string {
  return `${localDate(value)}T${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}.${String(value.getMilliseconds()).padStart(3, "0")}`;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}
