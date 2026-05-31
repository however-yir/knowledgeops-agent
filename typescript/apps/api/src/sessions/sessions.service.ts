import { Injectable } from "@nestjs/common";
import type { PagedResult, SessionBranch, SessionState } from "@knowledgeops/shared";

import { PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class SessionsService {
  constructor(private readonly store: PlatformStore) {}

  list(page: number, pageSize: number, includeArchived: boolean): PagedResult<SessionState> {
    const all = [...this.store.sessions.values()].filter((session) => includeArchived || !session.archived);
    const start = (Math.max(page, 1) - 1) * pageSize;
    return {
      items: all.slice(start, start + pageSize),
      total: all.length,
      page,
      pageSize
    };
  }

  upsert(sessionId: string, payload: SessionState): SessionState {
    const normalized = { ...payload, id: sessionId, updatedAt: Date.now() };
    this.store.sessions.set(sessionId, normalized);
    this.store.persist();
    return normalized;
  }

  get(sessionId: string): SessionState {
    return this.store.sessions.get(sessionId) ?? this.upsert(sessionId, {
      id: sessionId,
      title: "New TS session",
      updatedAt: Date.now(),
      modelProfile: "balanced",
      streaming: false,
      pinned: false,
      archived: false,
      workspaceId: "default",
      activeBranchId: "main",
      branches: [{
        id: "main",
        title: "Main",
        parentBranchId: null,
        parentMessageId: null,
        updatedAt: Date.now(),
        messages: [],
        traceSteps: []
      }]
    });
  }

  setPinned(sessionId: string, value: boolean): SessionState {
    const session = this.get(sessionId);
    session.pinned = value;
    session.updatedAt = Date.now();
    this.store.persist();
    return session;
  }

  setArchived(sessionId: string, value: boolean): SessionState {
    const session = this.get(sessionId);
    session.archived = value;
    session.updatedAt = Date.now();
    this.store.persist();
    return session;
  }

  compare(sessionId: string, sourceBranchId: string, targetBranchId: string) {
    const session = this.get(sessionId);
    const source = session.branches.find((branch) => branch.id === sourceBranchId);
    const target = session.branches.find((branch) => branch.id === targetBranchId);
    const sourceMessages = source?.messages ?? [];
    const targetMessages = target?.messages ?? [];
    const targetIds = new Set(targetMessages.map((message) => message.id));
    const sourceIds = new Set(sourceMessages.map((message) => message.id));
    const sourceOnly = sourceMessages.filter((message) => !targetIds.has(message.id));
    const targetOnly = targetMessages.filter((message) => !sourceIds.has(message.id));
    return {
      sourceBranchId,
      targetBranchId,
      sourceMessageCount: sourceMessages.length,
      targetMessageCount: targetMessages.length,
      commonMessageCount: sourceMessages.filter((message) => targetIds.has(message.id)).length,
      sourceOnlyCount: sourceOnly.length,
      targetOnlyCount: targetOnly.length,
      sourceOnlyPreview: sourceOnly.slice(0, 3).map((message) => message.content),
      targetOnlyPreview: targetOnly.slice(0, 3).map((message) => message.content)
    };
  }

  merge(sessionId: string, sourceBranchId: string, targetBranchId: string, title?: string) {
    const session = this.get(sessionId);
    const source = session.branches.find((branch) => branch.id === sourceBranchId);
    const target = session.branches.find((branch) => branch.id === targetBranchId);
    const mergedBranch: SessionBranch = {
      id: `merge-${Date.now()}`,
      title: title || "Merged branch",
      parentBranchId: target?.id ?? null,
      parentMessageId: null,
      updatedAt: Date.now(),
      messages: mergeMessages(target?.messages ?? [], source?.messages ?? []),
      traceSteps: [...(target?.traceSteps ?? []), ...(source?.traceSteps ?? [])]
    };
    session.branches.push(mergedBranch);
    session.activeBranchId = mergedBranch.id;
    session.updatedAt = Date.now();
    this.store.persist();
    return {
      session,
      mergedBranch,
      mergedMessageCount: mergedBranch.messages.length
    };
  }
}

function mergeMessages(target: SessionBranch["messages"], source: SessionBranch["messages"]): SessionBranch["messages"] {
  const seen = new Set(target.map((message) => message.id));
  return [...target, ...source.filter((message) => !seen.has(message.id))];
}
