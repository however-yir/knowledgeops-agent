import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { Injectable } from "@nestjs/common";
import type { IngestionJob, SessionState } from "@knowledgeops/shared";

import { env } from "../config/env.js";

export interface ApiKeyRecord {
  keyHash: string;
  keyName: string;
  roleName: string;
  tenantId: string;
  enabled: boolean;
  expiresAt?: string;
}

export interface RefreshTokenRecord {
  token: string;
  principal: string;
  roles: string[];
  tenantId: string;
  expiresAt: string;
}

export interface AuthIdentity {
  principal: string;
  roles: string[];
  permissions: string[];
  tenantId: string;
  source: "api_key" | "jwt";
}

export interface IngestionJobRecord extends IngestionJob {
  tenantId: string;
  sourceType: string;
  filePath: string;
  idempotencyKey: string;
  contentHash: string;
  rawText: string;
  nextRetryAt?: string;
}

export interface KnowledgeChunk {
  chunkId: string;
  tenantId: string;
  chatId: string;
  jobId: string;
  fileName: string;
  sourceType: string;
  chunkIndex: number;
  content: string;
  tokenSet: Set<string>;
  createdAt: string;
}

export interface WorkflowTask {
  taskId: string;
  tenantId: string;
  type: string;
  status: string;
  userInput: string;
  finalOutput?: string;
  modelProfile?: string;
  chatId?: string;
  sessionId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowEvent {
  eventId: string;
  taskId: string;
  eventType: string;
  payload: unknown;
  createdAt: string;
}

export interface EvalDataset {
  datasetId: string;
  tenantId: string;
  name: string;
  description?: string;
  baselineRunId?: string;
  cases: Array<Record<string, unknown>>;
  createdAt: string;
  updatedAt: string;
}

export interface EvalRun {
  runId: string;
  datasetId: string;
  tenantId: string;
  status: string;
  modelProfile: string;
  metrics: Record<string, number>;
  results: Array<Record<string, unknown>>;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  errorMessage?: string;
}

export interface HistorySessionRecord {
  tenantId: string;
  type: string;
  chatId: string;
  conversationId: string;
  updatedAt: string;
}

export interface ConversationRecord {
  tenantId: string;
  conversationId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
}

@Injectable()
export class PlatformStore {
  readonly apiKeys = new Map<string, ApiKeyRecord>();
  readonly refreshTokens = new Map<string, RefreshTokenRecord>();
  readonly ingestionJobs = new Map<string, IngestionJobRecord>();
  readonly idempotencyIndex = new Map<string, string>();
  readonly knowledgeChunks: KnowledgeChunk[] = [];
  readonly sessions = new Map<string, SessionState>();
  readonly workflowTasks = new Map<string, WorkflowTask>();
  readonly workflowEvents = new Map<string, WorkflowEvent[]>();
  readonly evalDatasets = new Map<string, EvalDataset>();
  readonly evalRuns = new Map<string, EvalRun>();
  readonly trustedActions = new Map<string, Record<string, unknown>>();
  readonly feedback: Array<Record<string, unknown>> = [];
  readonly auditLogs: Array<Record<string, unknown>> = [];
  readonly memoryItems: Array<Record<string, unknown>> = [];
  readonly graphEntities: Array<Record<string, unknown>> = [];
  readonly historySessions = new Map<string, HistorySessionRecord>();
  readonly conversations: ConversationRecord[] = [];

  constructor() {
    this.load();
    this.apiKeys.set(sha256Hex(env.APP_DEMO_API_KEY), {
      keyHash: sha256Hex(env.APP_DEMO_API_KEY),
      keyName: "ts-local-demo-admin-key",
      roleName: "ADMIN",
      tenantId: "public",
      enabled: true
    });
  }

  persist(): void {
    if (env.NODE_ENV === "test") {
      return;
    }
    mkdirSync(dirname(env.APP_STATE_FILE), { recursive: true });
    writeFileSync(env.APP_STATE_FILE, JSON.stringify({
      apiKeys: [...this.apiKeys.values()],
      refreshTokens: [...this.refreshTokens.values()],
      ingestionJobs: [...this.ingestionJobs.values()],
      idempotencyIndex: [...this.idempotencyIndex.entries()],
      knowledgeChunks: this.knowledgeChunks.map((chunk) => ({ ...chunk, tokenSet: undefined })),
      sessions: [...this.sessions.values()],
      workflowTasks: [...this.workflowTasks.values()],
      workflowEvents: [...this.workflowEvents.entries()],
      evalDatasets: [...this.evalDatasets.values()],
      evalRuns: [...this.evalRuns.values()],
      feedback: this.feedback,
      auditLogs: this.auditLogs,
      memoryItems: this.memoryItems,
      graphEntities: this.graphEntities,
      historySessions: [...this.historySessions.values()],
      conversations: this.conversations
    }, null, 2));
  }

  private load(): void {
    if (env.NODE_ENV === "test") {
      return;
    }
    if (!existsSync(env.APP_STATE_FILE)) {
      return;
    }
    const raw = JSON.parse(readFileSync(env.APP_STATE_FILE, "utf8")) as {
      apiKeys?: ApiKeyRecord[];
      refreshTokens?: RefreshTokenRecord[];
      ingestionJobs?: IngestionJobRecord[];
      idempotencyIndex?: [string, string][];
      knowledgeChunks?: Array<Omit<KnowledgeChunk, "tokenSet">>;
      sessions?: SessionState[];
      workflowTasks?: WorkflowTask[];
      workflowEvents?: [string, WorkflowEvent[]][];
      evalDatasets?: EvalDataset[];
      evalRuns?: EvalRun[];
      feedback?: Array<Record<string, unknown>>;
      auditLogs?: Array<Record<string, unknown>>;
      memoryItems?: Array<Record<string, unknown>>;
      graphEntities?: Array<Record<string, unknown>>;
      historySessions?: HistorySessionRecord[];
      conversations?: ConversationRecord[];
    };
    raw.apiKeys?.forEach((record) => this.apiKeys.set(record.keyHash, record));
    raw.refreshTokens?.forEach((record) => this.refreshTokens.set(record.token, record));
    raw.ingestionJobs?.forEach((record) => this.ingestionJobs.set(`${record.tenantId}:${record.jobId}`, record));
    raw.idempotencyIndex?.forEach(([key, value]) => this.idempotencyIndex.set(key, value));
    raw.knowledgeChunks?.forEach((chunk) => this.knowledgeChunks.push({ ...chunk, tokenSet: new Set(chunk.content.split(/\s+/)) }));
    raw.sessions?.forEach((session) => this.sessions.set(session.id, session));
    raw.workflowTasks?.forEach((task) => this.workflowTasks.set(task.taskId, task));
    raw.workflowEvents?.forEach(([taskId, events]) => this.workflowEvents.set(taskId, events));
    raw.evalDatasets?.forEach((dataset) => this.evalDatasets.set(dataset.datasetId, dataset));
    raw.evalRuns?.forEach((run) => this.evalRuns.set(run.runId, run));
    this.feedback.push(...(raw.feedback ?? []));
    this.auditLogs.push(...(raw.auditLogs ?? []));
    this.memoryItems.push(...(raw.memoryItems ?? []));
    this.graphEntities.push(...(raw.graphEntities ?? []));
    raw.historySessions?.forEach((session) => this.historySessions.set(historyKey(session.tenantId, session.type, session.chatId), session));
    this.conversations.push(...(raw.conversations ?? []));
  }
}

export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function historyKey(tenantId: string, type: string, chatId: string): string {
  return `${tenantId}:${type}:${chatId}`;
}
