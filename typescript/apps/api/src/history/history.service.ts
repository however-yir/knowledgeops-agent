import { Injectable } from "@nestjs/common";
import type { PagedResult } from "@knowledgeops/shared";

import { nowIso } from "../common/ids.js";
import { PlatformStore, historyKey } from "../platform/platform.store.js";

export interface MessageVO {
  role: "user" | "assistant" | "system" | "";
  content: string;
}

@Injectable()
export class HistoryService {
  constructor(private readonly store: PlatformStore) {}

  saveSession(tenantId: string, type: string, chatId: string): void {
    const conversationId = buildConversationId(type, chatId);
    const key = historyKey(tenantId, type, chatId);
    this.store.historySessions.set(key, {
      tenantId,
      type,
      chatId,
      conversationId,
      updatedAt: nowIso()
    });
    this.store.persist();
  }

  appendExchange(tenantId: string, type: string, chatId: string, prompt: string, answer: string): void {
    const conversationId = buildConversationId(type, chatId);
    this.saveSession(tenantId, type, chatId);
    const createdAtMs = Date.now();
    if (prompt.trim()) {
      this.store.conversations.push({
        tenantId,
        conversationId,
        role: "user",
        content: prompt,
        createdAt: new Date(createdAtMs).toISOString()
      });
    }
    if (answer.trim()) {
      this.store.conversations.push({
        tenantId,
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
    const all = [...this.store.historySessions.values()]
      .filter((session) => session.tenantId === tenantId && session.type === type)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize).map((session) => session.chatId),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }

  listMessages(tenantId: string, type: string, chatId: string, page: number, pageSize: number): PagedResult<MessageVO> {
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const conversationId = buildConversationId(type, chatId);
    const all = this.store.conversations
      .filter((message) => message.tenantId === tenantId && message.conversationId === conversationId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map((message) => ({ role: message.role, content: message.content }));
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }
}

export function buildConversationId(type: string, chatId: string): string {
  if (!type.trim() || !chatId.trim()) {
    throw new Error("type and chatId must not be blank");
  }
  return `${type}::${chatId}`;
}
