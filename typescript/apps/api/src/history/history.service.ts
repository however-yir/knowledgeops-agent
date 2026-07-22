import { Injectable } from "@nestjs/common";
import type { PagedResult } from "@knowledgeops/shared";

import { normalizeTenant } from "../common/tenant.js";
import { PlatformStore } from "../platform/platform.store.js";

export interface MessageVO {
  role: "user" | "assistant" | "system" | "";
  content: string;
}

@Injectable()
export class HistoryService {
  constructor(private readonly store: PlatformStore) {}

  saveSession(_tenantId: string, type: string, chatId: string): void {
    buildConversationId(type, chatId);
  }

  appendExchange(tenantId: string, type: string, chatId: string, prompt: string, answer: string): void {
    const tenant = normalizeTenant(tenantId);
    const conversationId = buildConversationId(type, chatId);
    const createdAtMs = Date.now();
    if (prompt.trim()) {
      this.store.conversations.push({
        tenantId: tenant,
        conversationId,
        role: "user",
        content: prompt,
        createdAt: new Date(createdAtMs).toISOString()
      });
    }
    if (answer.trim()) {
      this.store.conversations.push({
        tenantId: tenant,
        conversationId,
        role: "assistant",
        content: answer,
        createdAt: new Date(createdAtMs + 1).toISOString()
      });
    }
    this.store.persist();
  }

  listChatIds(tenantId: string, type: string, page: number, pageSize: number): PagedResult<string> {
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const tenant = normalizeTenant(tenantId);
    const prefix = `${type}::`;
    const latestByConversation = new Map<string, string>();
    for (const message of this.store.conversations) {
      if (normalizeTenant(message.tenantId) !== tenant || !message.conversationId.startsWith(prefix)) {
        continue;
      }
      const previous = latestByConversation.get(message.conversationId);
      if (!previous || previous < message.createdAt) {
        latestByConversation.set(message.conversationId, message.createdAt);
      }
    }
    const all = [...latestByConversation]
      .sort((a, b) => b[1].localeCompare(a[1]))
      .map(([conversationId]) => conversationId.slice(prefix.length));
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }

  listMessages(tenantId: string, type: string, chatId: string, page: number, pageSize: number): PagedResult<MessageVO> {
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const all = this.messagesNewestFirst(tenantId, buildConversationId(type, chatId));
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize).map(toMessageVO),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }

  latestMessages(tenantId: string, type: string, chatId: string, lastN: number): MessageVO[] {
    if (lastN <= 0) {
      return [];
    }
    return this.messagesNewestFirst(tenantId, buildConversationId(type, chatId))
      .slice(0, lastN)
      .map(toMemoryMessageVO)
      .filter((message): message is MessageVO => message !== undefined)
      .reverse();
  }

  private messagesNewestFirst(tenantId: string, conversationId: string) {
    const tenant = normalizeTenant(tenantId);
    return this.store.conversations
      .filter((message) => normalizeTenant(message.tenantId) === tenant && message.conversationId === conversationId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
}

export function buildConversationId(type: string, chatId: string): string {
  if (!type.trim() || !chatId.trim()) {
    throw new Error("type and chatId must not be blank");
  }
  return `${type}::${chatId}`;
}

function toMessageVO(message: { role: unknown; content: string }): MessageVO {
  return { role: mapRole(message.role), content: message.content };
}

function toMemoryMessageVO(message: { role: unknown; content: string }): MessageVO | undefined {
  const role = mapRole(message.role);
  return role ? { role, content: message.content } : undefined;
}

function mapRole(value: unknown): MessageVO["role"] {
  switch (String(value ?? "").toUpperCase()) {
    case "USER":
      return "user";
    case "ASSISTANT":
      return "assistant";
    case "SYSTEM":
      return "system";
    default:
      return "";
  }
}
