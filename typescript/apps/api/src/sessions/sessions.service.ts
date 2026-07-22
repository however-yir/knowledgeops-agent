import { Injectable, NotFoundException } from "@nestjs/common";
import type { PagedResult, SessionBranch, SessionState } from "@knowledgeops/shared";

import { normalizeTenant } from "../common/tenant.js";
import { PlatformStore, sessionKey } from "../platform/platform.store.js";

@Injectable()
export class SessionsService {
  constructor(private readonly store: PlatformStore) {}

  list(
    tenantId: string,
    page: number,
    pageSize: number,
    includeArchived: boolean,
    search?: string,
    workspaceId?: string
  ): PagedResult<SessionState> {
    const tenant = normalizeTenant(tenantId);
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const keyword = search?.trim().toLowerCase();
    const all = [...this.store.sessions.values()]
      .filter((session) => normalizeTenant(session.tenantId) === tenant)
      .filter((session) => includeArchived || !session.archived)
      .filter((session) => !workspaceId || session.workspaceId === workspaceId)
      .filter((session) => !keyword || `${session.title} ${session.id}`.toLowerCase().includes(keyword))
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt);
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }

  upsert(tenantId: string, sessionId: string, payload: SessionState): SessionState {
    const tenant = normalizeTenant(tenantId);
    const normalized = {
      ...payload,
      id: sessionId,
      tenantId: tenant,
      updatedAt: Date.now()
    };
    this.store.sessions.set(sessionKey(tenant, sessionId), normalized);
    this.store.persist();
    return normalized;
  }

  get(tenantId: string, sessionId: string): SessionState {
    const session = this.store.sessions.get(sessionKey(normalizeTenant(tenantId), sessionId));
    if (!session) {
      throw new NotFoundException("session not found");
    }
    return session;
  }

  setPinned(tenantId: string, sessionId: string, value: boolean): SessionState {
    const session = this.get(tenantId, sessionId);
    session.pinned = value;
    session.updatedAt = Date.now();
    this.store.persist();
    return session;
  }

  setArchived(tenantId: string, sessionId: string, value: boolean): SessionState {
    const session = this.get(tenantId, sessionId);
    session.archived = value;
    session.updatedAt = Date.now();
    this.store.persist();
    return session;
  }

  compare(tenantId: string, sessionId: string, sourceBranchId: string, targetBranchId: string) {
    const session = this.get(tenantId, sessionId);
    const source = branchOrThrow(session, sourceBranchId);
    const target = branchOrThrow(session, targetBranchId);
    const sourceMessages = source.messages ?? [];
    const targetMessages = target.messages ?? [];
    const targetFingerprints = new Set(targetMessages.map(messageFingerprint));
    const sourceFingerprints = new Set(sourceMessages.map(messageFingerprint));
    const sourceOnly = sourceMessages.filter((message) => !targetFingerprints.has(messageFingerprint(message)));
    const targetOnly = targetMessages.filter((message) => !sourceFingerprints.has(messageFingerprint(message)));
    return {
      sourceBranchId,
      targetBranchId,
      sourceMessageCount: sourceMessages.length,
      targetMessageCount: targetMessages.length,
      commonMessageCount: sourceMessages.filter((message) => targetFingerprints.has(messageFingerprint(message))).length,
      sourceOnlyCount: sourceOnly.length,
      targetOnlyCount: targetOnly.length,
      sourceOnlyPreview: sourceOnly.slice(0, 5).map((message) => preview(message.content)),
      targetOnlyPreview: targetOnly.slice(0, 5).map((message) => preview(message.content))
    };
  }

  merge(tenantId: string, sessionId: string, sourceBranchId: string, targetBranchId: string, title?: string) {
    const session = this.get(tenantId, sessionId);
    const source = branchOrThrow(session, sourceBranchId);
    const target = branchOrThrow(session, targetBranchId);
    const mergedBranch: SessionBranch = {
      id: `merge-${Date.now()}`,
      title: title?.trim() || `${target.title || "Branch"} · merge`,
      parentBranchId: target.id,
      parentMessageId: target.parentMessageId,
      updatedAt: Date.now(),
      messages: mergeMessages(target.messages ?? [], source.messages ?? []),
      traceSteps: [...(target.traceSteps ?? [])]
    };
    session.branches.unshift(mergedBranch);
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

function branchOrThrow(session: SessionState, branchId: string): SessionBranch {
  const branch = session.branches.find((candidate) => candidate.id === branchId);
  if (!branch) {
    throw new NotFoundException("branch not found");
  }
  return branch;
}

function messageFingerprint(message: SessionBranch["messages"][number]): string {
  return `${message.role}::${message.content.replace(/\s+/g, " ").trim()}`;
}

function mergeMessages(target: SessionBranch["messages"], source: SessionBranch["messages"]): SessionBranch["messages"] {
  const seen = new Set(target.map(messageFingerprint));
  return [...target, ...source.filter((message) => !seen.has(messageFingerprint(message)))];
}

function preview(value: string): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length <= 120 ? normalized : `${normalized.slice(0, 120)}...`;
}
