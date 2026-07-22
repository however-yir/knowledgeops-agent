import { BadRequestException, Injectable } from "@nestjs/common";
import type { PagedResult, SessionBranch, SessionMessage, SessionState } from "@knowledgeops/shared";

import { normalizeTenant } from "../common/tenant.js";
import { PlatformStore, sessionKey } from "../platform/platform.store.js";

export type SessionPayload = Partial<Omit<SessionState, "id">>;

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
    const keyword = clean(search)?.toLowerCase();
    const workspace = workspaceId;
    const all = [...this.store.sessions.values()]
      .filter((session) => normalizeTenant(session.tenantId) === tenant)
      .filter((session) => includeArchived || !session.archived)
      .filter((session) => !workspace || workspace === "all" || session.workspaceId === workspace)
      .filter((session) => !keyword || `${session.title} ${session.id}`.toLowerCase().includes(keyword))
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt);
    const start = (safePage - 1) * safePageSize;
    return {
      items: all.slice(start, start + safePageSize).map(toPublicSession),
      total: all.length,
      page: safePage,
      pageSize: safePageSize
    };
  }

  upsert(tenantId: string, sessionId: string, payload: SessionPayload | null | undefined): SessionState {
    if (!payload) {
      throw new BadRequestException("session payload is required");
    }
    const normalizedSessionId = clean(sessionId);
    if (!normalizedSessionId) {
      throw new BadRequestException("session id is required");
    }
    const tenant = normalizeTenant(tenantId);
    const branches = Array.isArray(payload.branches) ? payload.branches : [];
    const normalized: SessionState = {
      id: normalizedSessionId,
      tenantId: tenant,
      title: hasText(payload.title) ? String(payload.title) : "新会话",
      updatedAt: payload.updatedAt ?? Date.now(),
      modelProfile: hasText(payload.modelProfile) ? String(payload.modelProfile) : "balanced",
      streaming: payload.streaming ?? true,
      pinned: payload.pinned === true,
      archived: payload.archived === true,
      workspaceId: hasText(payload.workspaceId) ? String(payload.workspaceId) : "default",
      activeBranchId: hasText(payload.activeBranchId) ? String(payload.activeBranchId) : branches[0]?.id ?? "",
      branches
    };
    normalized.updatedAt = Date.now();
    this.store.sessions.set(sessionKey(tenant, normalizedSessionId), normalized);
    this.store.persist();
    return toPublicSession(normalized);
  }

  get(tenantId: string, sessionId: string): SessionState {
    const normalizedSessionId = clean(sessionId);
    if (!normalizedSessionId) {
      throw new BadRequestException("session id is required");
    }
    const session = this.store.sessions.get(sessionKey(normalizeTenant(tenantId), normalizedSessionId));
    if (!session) {
      throw new BadRequestException("session not found");
    }
    return toPublicSession(session);
  }

  setPinned(tenantId: string, sessionId: string, value: boolean): SessionState {
    const session = this.get(tenantId, sessionId);
    return this.upsert(tenantId, sessionId, { ...session, pinned: value });
  }

  setArchived(tenantId: string, sessionId: string, value: boolean): SessionState {
    const session = this.get(tenantId, sessionId);
    return this.upsert(tenantId, sessionId, { ...session, archived: value });
  }

  compare(tenantId: string, sessionId: string, sourceBranchId: string, targetBranchId: string) {
    const session = this.get(tenantId, sessionId);
    const source = branchOrThrow(session, sourceBranchId);
    const target = branchOrThrow(session, targetBranchId);
    const sourceMessages = source.messages ?? [];
    const targetMessages = target.messages ?? [];
    const sourceFingerprints = new Set(sourceMessages.map(messageFingerprint));
    const targetFingerprints = new Set(targetMessages.map(messageFingerprint));
    const sourceOnlyFingerprints = difference(sourceFingerprints, targetFingerprints);
    const targetOnlyFingerprints = difference(targetFingerprints, sourceFingerprints);
    return {
      sourceBranchId,
      targetBranchId,
      sourceMessageCount: sourceMessages.length,
      targetMessageCount: targetMessages.length,
      commonMessageCount: intersectionSize(sourceFingerprints, targetFingerprints),
      sourceOnlyCount: sourceOnlyFingerprints.size,
      targetOnlyCount: targetOnlyFingerprints.size,
      sourceOnlyPreview: messagePreviews(sourceMessages, sourceOnlyFingerprints),
      targetOnlyPreview: messagePreviews(targetMessages, targetOnlyFingerprints)
    };
  }

  merge(tenantId: string, sessionId: string, sourceBranchId: string, targetBranchId: string, title?: string) {
    const session = this.get(tenantId, sessionId);
    const source = branchOrThrow(session, sourceBranchId);
    const target = branchOrThrow(session, targetBranchId);
    const mergedBranch: SessionBranch = {
      id: `branch-merge-${Date.now()}-${Math.floor(Math.random() * 100000)}`,
      title: clean(title) ?? `${clean(target.title) ?? "分支"} · merge`,
      parentBranchId: target.id,
      parentMessageId: target.parentMessageId,
      updatedAt: Date.now(),
      messages: mergeMessages(target.messages ?? [], source.messages ?? []),
      traceSteps: target.traceSteps ?? []
    };
    const saved = this.upsert(tenantId, sessionId, {
      ...session,
      branches: [mergedBranch, ...(session.branches ?? [])],
      activeBranchId: mergedBranch.id,
      updatedAt: Date.now()
    });
    return {
      session: saved,
      mergedBranch,
      mergedMessageCount: mergedBranch.messages.length
    };
  }

  attachWorkflowSnapshot(
    tenantId: string,
    sessionId: string,
    branchId: string,
    messageId: string,
    taskId: string,
    traceId: string | undefined,
    memorySnapshot: Array<Record<string, unknown>>,
    workflowState: Record<string, unknown>
  ): SessionState {
    const session = this.get(tenantId, sessionId);
    for (const branch of session.branches ?? []) {
      if (branch.id !== branchId) {
        continue;
      }
      for (const message of branch.messages ?? []) {
        if (message.id !== messageId) {
          continue;
        }
        message.taskId = taskId;
        message.traceId = traceId;
        message.memorySnapshot = memorySnapshot;
        message.workflowState = workflowState;
      }
    }
    return this.upsert(tenantId, sessionId, session);
  }
}

function toPublicSession(session: SessionState): SessionState {
  const { tenantId: _tenantId, ...publicSession } = session;
  return {
    ...publicSession,
    branches: (session.branches ?? []).map((branch) => ({
      ...branch,
      messages: (branch.messages ?? []).map((message) => ({ ...message })),
      traceSteps: [...(branch.traceSteps ?? [])]
    }))
  };
}

function branchOrThrow(session: SessionState, branchId: string): SessionBranch {
  if (!hasText(branchId)) {
    throw new BadRequestException("branch id is required");
  }
  const branch = session.branches.find((candidate) => candidate.id === branchId);
  if (!branch) {
    throw new BadRequestException("branch not found");
  }
  return branch;
}

function messageFingerprint(message: SessionMessage | null | undefined): string {
  if (!message) {
    return "null";
  }
  return `${clean(message.role) ?? "unknown"}::${normalizeContent(message.content)}`;
}

function mergeMessages(target: SessionMessage[], source: SessionMessage[]): SessionMessage[] {
  const merged = target.map(copyMessage);
  const targetFingerprints = new Set(merged.map(messageFingerprint));
  const existingIds = new Set(merged.map((message) => clean(message.id)).filter((id): id is string => Boolean(id)));
  for (const original of source) {
    const fingerprint = messageFingerprint(original);
    if (targetFingerprints.has(fingerprint)) {
      continue;
    }
    const message = copyMessage(original);
    ensureUniqueMessageId(message, existingIds, fingerprint);
    merged.push(message);
    targetFingerprints.add(fingerprint);
  }
  return merged;
}

function copyMessage(message: SessionMessage): SessionMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: message.createdAt,
    state: message.state,
    citations: message.citations ? [...message.citations] : [],
    evidence: message.evidence ? [...message.evidence] : []
  };
}

function ensureUniqueMessageId(message: SessionMessage, existingIds: Set<string>, fingerprint: string): void {
  let id = hasText(message.id) ? message.id : `merged-${Date.now()}-${positiveJavaHash(fingerprint)}`;
  if (existingIds.has(id)) {
    id = `${id}-m${existingIds.size}`;
  }
  message.id = id;
  existingIds.add(id);
}

function positiveJavaHash(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash * 31) + value.charCodeAt(index)) | 0;
  }
  return hash & 0x7fffffff;
}

function messagePreviews(messages: SessionMessage[], selected: Set<string>): string[] {
  if (selected.size === 0) {
    return [];
  }
  const previews: string[] = [];
  for (const message of messages) {
    if (!selected.has(messageFingerprint(message))) {
      continue;
    }
    previews.push(preview(message.content));
    if (previews.length >= 5) {
      break;
    }
  }
  return previews;
}

function difference(left: Set<string>, right: Set<string>): Set<string> {
  return new Set([...left].filter((value) => !right.has(value)));
}

function intersectionSize(left: Set<string>, right: Set<string>): number {
  return [...left].filter((value) => right.has(value)).length;
}

function preview(value: string): string {
  const normalized = normalizeContent(value);
  return normalized.length <= 120 ? normalized : `${normalized.slice(0, 120)}...`;
}

function normalizeContent(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function clean(value: unknown): string | undefined {
  const text = String(value ?? "").trim();
  return text || undefined;
}

function hasText(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}
