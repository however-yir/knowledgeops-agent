import { createHash } from "node:crypto";

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

@Injectable()
export class PlatformStore {
  readonly apiKeys = new Map<string, ApiKeyRecord>();
  readonly refreshTokens = new Map<string, RefreshTokenRecord>();
  readonly ingestionJobs = new Map<string, IngestionJob>();
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

  constructor() {
    this.apiKeys.set(sha256Hex(env.APP_DEMO_API_KEY), {
      keyHash: sha256Hex(env.APP_DEMO_API_KEY),
      keyName: "ts-local-demo-admin-key",
      roleName: "ADMIN",
      tenantId: "public",
      enabled: true
    });
  }
}

export function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
