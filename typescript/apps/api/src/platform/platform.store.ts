import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { Injectable } from "@nestjs/common";
import type { IngestionJob, SessionState } from "@knowledgeops/shared";

import { tokenize } from "../common/text.js";
import { env } from "../config/env.js";

export interface ApiKeyRecord {
  keyHash: string;
  keyName: string;
  roleName: string;
  tenantId: string;
  enabled: boolean;
  lastUsedAt?: string;
  expiresAt?: string;
  revokedAt?: string;
  revokedReason?: string;
  rotatedFromId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface RefreshTokenRecord {
  tokenHash: string;
  token?: string;
  principal: string;
  roles: string[];
  tenantId: string;
  expiresAt: string;
  revokedAt?: string;
  createdAt?: string;
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
  updatedAt?: string;
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
  vector: number[];
  metadata: Record<string, unknown>;
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

export interface WorkflowStep {
  stepId: string;
  taskId: string;
  agentName: string;
  status: string;
  stepOrder: number;
  thought?: string;
  action?: string;
  actionInput?: Record<string, unknown>;
  observation?: unknown;
  modelProfile?: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  errorMessage?: string;
  startedAt: string;
  endedAt?: string;
}

export interface WorkflowEvent {
  eventId: string;
  taskId: string;
  stepId?: string;
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

export interface TenantBudgetRecord {
  tenantId: string;
  monthlyBudgetUsd: number;
  hardLimitEnabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface TenantUsageDailyRecord {
  tenantId: string;
  usageDate: string;
  requestCount: number;
  inputTokens: number;
  outputTokens: number;
  totalCostUsd: number;
  createdAt: string;
  updatedAt: string;
}

export interface ModelAbExposureRecord {
  tenantId: string;
  experimentKey: string;
  subjectKey: string;
  endpoint: string;
  bucket: number;
  variant: string;
  routedProfile: string;
  createdAt: string;
}

export interface MemoryItemRecord {
  memoryId: string;
  tenantId: string;
  userId: string;
  type: "short" | "long" | "task" | "fact" | string;
  content: string;
  source?: string;
  sourceTaskId?: string;
  confidence: number;
  expiresAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryEventRecord {
  eventId: string;
  memoryId: string;
  action: string;
  reason: string;
  createdAt: string;
}

export interface KgEntityRecord {
  entityId: string;
  tenantId: string;
  name: string;
  type: string;
  description?: string;
  aliases: string[];
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface KgRelationRecord {
  relationId: string;
  tenantId: string;
  sourceEntityId: string;
  targetEntityId: string;
  relationType: string;
  weight: number;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface KgFactRecord {
  factId: string;
  tenantId: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  source?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface HarnessEventRecord {
  eventId: string;
  tenantId: string;
  action: string;
  source: string;
  status: string;
  latencyMs: number;
  payload: unknown;
  createdAt: string;
}

export interface CourseRecord {
  id: number;
  name: string;
  edu?: number;
  type?: string;
  price?: number;
  duration?: number;
}

export interface SchoolRecord {
  id: number;
  name: string;
  city?: string;
}

export interface CourseReservationRecord {
  id: number;
  course: string;
  studentName: string;
  contactInfo: string;
  school: string;
  remark?: string;
}

interface PersistedState {
  apiKeys?: ApiKeyRecord[];
  refreshTokens?: RefreshTokenRecord[];
  ingestionJobs?: IngestionJobRecord[];
  idempotencyIndex?: [string, string][];
  knowledgeChunks?: Array<Omit<KnowledgeChunk, "tokenSet">>;
  sessions?: SessionState[];
  workflowTasks?: WorkflowTask[];
  workflowSteps?: [string, WorkflowStep[]][];
  workflowEvents?: [string, WorkflowEvent[]][];
  evalDatasets?: EvalDataset[];
  evalRuns?: EvalRun[];
  trustedActions?: [string, Record<string, unknown>][];
  feedback?: Array<Record<string, unknown>>;
  auditLogs?: Array<Record<string, unknown>>;
  memoryItems?: MemoryItemRecord[];
  memoryEvents?: [string, MemoryEventRecord[]][];
  graphEntities?: KgEntityRecord[];
  graphRelations?: KgRelationRecord[];
  graphFacts?: KgFactRecord[];
  historySessions?: HistorySessionRecord[];
  conversations?: ConversationRecord[];
  tenantBudgets?: TenantBudgetRecord[];
  tenantUsageDaily?: TenantUsageDailyRecord[];
  modelExposures?: ModelAbExposureRecord[];
  harnessEvents?: HarnessEventRecord[];
  courses?: CourseRecord[];
  schools?: SchoolRecord[];
  courseReservations?: CourseReservationRecord[];
  metrics?: Record<string, number>;
}

@Injectable()
export class PlatformStore {
  private readonly persistenceSinks: Array<() => void | Promise<void>> = [];
  private persistenceTail: Promise<void> = Promise.resolve();
  private persistenceFailure: Error | undefined;

  readonly apiKeys = new Map<string, ApiKeyRecord>();
  readonly refreshTokens = new Map<string, RefreshTokenRecord>();
  readonly ingestionJobs = new Map<string, IngestionJobRecord>();
  readonly idempotencyIndex = new Map<string, string>();
  readonly knowledgeChunks: KnowledgeChunk[] = [];
  readonly sessions = new Map<string, SessionState>();
  readonly workflowTasks = new Map<string, WorkflowTask>();
  readonly workflowSteps = new Map<string, WorkflowStep[]>();
  readonly workflowEvents = new Map<string, WorkflowEvent[]>();
  readonly evalDatasets = new Map<string, EvalDataset>();
  readonly evalRuns = new Map<string, EvalRun>();
  readonly trustedActions = new Map<string, Record<string, unknown>>();
  readonly feedback: Array<Record<string, unknown>> = [];
  readonly auditLogs: Array<Record<string, unknown>> = [];
  readonly memoryItems: MemoryItemRecord[] = [];
  readonly memoryEvents = new Map<string, MemoryEventRecord[]>();
  readonly deletedMemoryIds = new Set<string>();
  readonly graphEntities: KgEntityRecord[] = [];
  readonly graphRelations: KgRelationRecord[] = [];
  readonly graphFacts: KgFactRecord[] = [];
  readonly historySessions = new Map<string, HistorySessionRecord>();
  readonly conversations: ConversationRecord[] = [];
  readonly tenantBudgets = new Map<string, TenantBudgetRecord>();
  readonly tenantUsageDaily = new Map<string, TenantUsageDailyRecord>();
  readonly modelExposures: ModelAbExposureRecord[] = [];
  readonly harnessEvents: HarnessEventRecord[] = [];
  readonly courses: CourseRecord[] = [];
  readonly schools: SchoolRecord[] = [];
  readonly courseReservations: CourseReservationRecord[] = [];
  readonly metrics = new Map<string, number>();

  constructor() {
    this.load();
    const demoHash = sha256Hex(env.APP_DEMO_API_KEY);
    this.apiKeys.set(demoHash, {
      keyHash: demoHash,
      keyName: "ts-local-demo-admin-key",
      roleName: "ADMIN",
      tenantId: "public",
      enabled: true,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
    this.seedBusinessCatalog();
  }

  persist(): void {
    if (env.NODE_ENV === "test") {
      return;
    }
    if (!env.APP_PRISMA_ENABLED) {
      mkdirSync(dirname(env.APP_STATE_FILE), { recursive: true });
      writeFileSync(env.APP_STATE_FILE, JSON.stringify({
      apiKeys: [...this.apiKeys.values()],
      refreshTokens: [...this.refreshTokens.values()],
      ingestionJobs: [...this.ingestionJobs.values()],
      idempotencyIndex: [...this.idempotencyIndex.entries()],
      knowledgeChunks: this.knowledgeChunks.map((chunk) => ({ ...chunk, tokenSet: undefined })),
      sessions: [...this.sessions.values()],
      workflowTasks: [...this.workflowTasks.values()],
      workflowSteps: [...this.workflowSteps.entries()],
      workflowEvents: [...this.workflowEvents.entries()],
      evalDatasets: [...this.evalDatasets.values()],
      evalRuns: [...this.evalRuns.values()],
      trustedActions: [...this.trustedActions.entries()],
      feedback: this.feedback,
      auditLogs: this.auditLogs,
      memoryItems: this.memoryItems,
      memoryEvents: [...this.memoryEvents.entries()],
      graphEntities: this.graphEntities,
      graphRelations: this.graphRelations,
      graphFacts: this.graphFacts,
      historySessions: [...this.historySessions.values()],
      conversations: this.conversations,
      tenantBudgets: [...this.tenantBudgets.values()],
      tenantUsageDaily: [...this.tenantUsageDaily.values()],
      modelExposures: this.modelExposures,
      harnessEvents: this.harnessEvents,
      courses: this.courses,
      schools: this.schools,
      courseReservations: this.courseReservations,
        metrics: Object.fromEntries(this.metrics.entries())
      } satisfies PersistedState, null, 2));
    }
    if (this.persistenceSinks.length > 0) {
      this.persistenceTail = this.persistenceTail
        .then(async () => {
          for (const sink of this.persistenceSinks) {
            await sink();
          }
          this.persistenceFailure = undefined;
        })
        .catch((error: unknown) => {
          this.persistenceFailure = error instanceof Error ? error : new Error(String(error));
        });
    }
  }

  registerPersistenceSink(sink: () => void | Promise<void>): void {
    this.persistenceSinks.push(sink);
  }

  async waitForPersistence(): Promise<void> {
    await this.persistenceTail;
    if (this.persistenceFailure) {
      throw this.persistenceFailure;
    }
  }

  persistenceHealthy(): boolean {
    return !this.persistenceFailure;
  }

  markMemoryDeleted(memoryId: string): void {
    this.deletedMemoryIds.add(memoryId);
  }

  incrementMetric(name: string, labels: Record<string, string | number | boolean | undefined> = {}, value = 1): void {
    const key = metricKey(name, labels);
    this.metrics.set(key, (this.metrics.get(key) ?? 0) + value);
  }

  private load(): void {
    if (env.NODE_ENV === "test" || env.APP_PRISMA_ENABLED || !existsSync(env.APP_STATE_FILE)) {
      return;
    }
    const raw = readState(env.APP_STATE_FILE);
    raw.apiKeys?.forEach((record) => this.apiKeys.set(record.keyHash, record));
    raw.refreshTokens?.forEach((record) => {
      const tokenHash = record.tokenHash || sha256Hex(record.token ?? "");
      this.refreshTokens.set(tokenHash, { ...record, tokenHash, token: undefined });
    });
    raw.ingestionJobs?.forEach((record) => this.ingestionJobs.set(`${record.tenantId}:${record.jobId}`, record));
    raw.idempotencyIndex?.forEach(([key, value]) => this.idempotencyIndex.set(key, value));
    raw.knowledgeChunks?.forEach((chunk) => this.knowledgeChunks.push({
      ...chunk,
      vector: Array.isArray(chunk.vector) ? chunk.vector : embeddingVector(chunk.content),
      metadata: chunk.metadata ?? {},
      tokenSet: tokenize(chunk.content)
    }));
    raw.sessions?.forEach((session) => this.sessions.set(sessionKey(session.tenantId ?? "public", session.id), session));
    raw.workflowTasks?.forEach((task) => this.workflowTasks.set(task.taskId, task));
    raw.workflowSteps?.forEach(([taskId, steps]) => this.workflowSteps.set(taskId, steps));
    raw.workflowEvents?.forEach(([taskId, events]) => this.workflowEvents.set(taskId, events));
    raw.evalDatasets?.forEach((dataset) => this.evalDatasets.set(dataset.datasetId, dataset));
    raw.evalRuns?.forEach((run) => this.evalRuns.set(run.runId, run));
    raw.trustedActions?.forEach(([token, request]) => this.trustedActions.set(token, request));
    this.feedback.push(...(raw.feedback ?? []));
    this.auditLogs.push(...(raw.auditLogs ?? []));
    this.memoryItems.push(...(raw.memoryItems ?? []));
    raw.memoryEvents?.forEach(([memoryId, events]) => this.memoryEvents.set(memoryId, events));
    this.graphEntities.push(...(raw.graphEntities ?? []));
    this.graphRelations.push(...(raw.graphRelations ?? []));
    this.graphFacts.push(...(raw.graphFacts ?? []));
    raw.historySessions?.forEach((session) => this.historySessions.set(historyKey(session.tenantId, session.type, session.chatId), session));
    this.conversations.push(...(raw.conversations ?? []));
    raw.tenantBudgets?.forEach((budget) => this.tenantBudgets.set(budget.tenantId, budget));
    raw.tenantUsageDaily?.forEach((usage) => this.tenantUsageDaily.set(tenantUsageKey(usage.tenantId, usage.usageDate), usage));
    this.modelExposures.push(...(raw.modelExposures ?? []));
    this.harnessEvents.push(...(raw.harnessEvents ?? []));
    this.courses.push(...(raw.courses ?? []));
    this.schools.push(...(raw.schools ?? []));
    this.courseReservations.push(...(raw.courseReservations ?? []));
    Object.entries(raw.metrics ?? {}).forEach(([key, value]) => this.metrics.set(key, value));
  }

  private seedBusinessCatalog(): void {
    if (this.courses.length === 0) {
      this.courses.push(
        { id: 1, name: "Java编程实战", edu: 0, type: "编程", price: 699900, duration: 90 },
        { id: 2, name: "Python数据分析", edu: 2, type: "编程", price: 799900, duration: 75 },
        { id: 3, name: "UI设计全链路", edu: 2, type: "设计", price: 599900, duration: 60 },
        { id: 4, name: "短视频运营", edu: 0, type: "自媒体", price: 399900, duration: 45 }
      );
    }
    if (this.schools.length === 0) {
      this.schools.push(
        { id: 1, name: "北京校区", city: "北京" },
        { id: 2, name: "上海校区", city: "上海" },
        { id: 3, name: "深圳校区", city: "深圳" }
      );
    }
  }
}

export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function historyKey(tenantId: string, type: string, chatId: string): string {
  return `${tenantId}:${type}:${chatId}`;
}

export function sessionKey(tenantId: string, sessionId: string): string {
  return `${tenantId}:${sessionId}`;
}

export function tenantUsageKey(tenantId: string, usageDate: string): string {
  return `${tenantId}:${usageDate}`;
}

export function embeddingVector(text: string, dimensions = 64): number[] {
  const vector = Array.from({ length: dimensions }, () => 0);
  for (const token of tokenize(text)) {
    const hash = createHash("sha256").update(token).digest();
    const index = hash[0] % dimensions;
    const sign = hash[1] % 2 === 0 ? 1 : -1;
    vector[index] += sign;
  }
  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0)) || 1;
  return vector.map((value) => value / norm);
}

function readState(path: string): PersistedState {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as PersistedState;
  } catch {
    return {};
  }
}

function metricKey(name: string, labels: Record<string, string | number | boolean | undefined>): string {
  const labelText = Object.entries(labels)
    .filter(([, value]) => value !== undefined)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}="${String(value).replace(/"/g, "'")}"`)
    .join(",");
  return labelText ? `${name}{${labelText}}` : name;
}
