import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";

import type { SessionState } from "@knowledgeops/shared";
import { tokenize } from "../common/text.js";
import { env } from "../config/env.js";
import {
  type ConversationRecord,
  embeddingVector,
  historyKey,
  type ModelAbExposureRecord,
  PlatformStore,
  sessionKey,
  sha256Hex,
  type TenantBudgetRecord,
  type TenantUsageDailyRecord,
  tenantUsageKey
} from "./platform.store.js";

interface AppendOnlySnapshot {
  auditLogs: Array<Record<string, unknown>>;
  feedback: Array<Record<string, unknown>>;
  exposures: ModelAbExposureRecord[];
  conversations: ConversationRecord[];
  auditEnd: number;
  feedbackEnd: number;
  exposureEnd: number;
  conversationEnd: number;
  deletedMemoryIds: string[];
}

type PrismaClientLike = Record<string, any> & {
  $connect?: () => Promise<void>;
  $disconnect?: () => Promise<void>;
  $transaction: {
    (actions: Array<Promise<unknown>>): Promise<unknown>;
    <T>(callback: (transaction: PrismaClientLike) => Promise<T>): Promise<T>;
  };
};

@Injectable()
export class PrismaPersistenceService implements OnModuleInit, OnModuleDestroy {
  private client: PrismaClientLike | undefined;
  private inFlight = false;
  private dirty = false;
  private lastAuditIndex = 0;
  private lastFeedbackIndex = 0;
  private lastExposureIndex = 0;
  private lastConversationIndex = 0;
  private committedBudgets = new Map<string, TenantBudgetRecord>();
  private committedUsage = new Map<string, TenantUsageDailyRecord>();

  constructor(private readonly store: PlatformStore) {}

  async onModuleInit(): Promise<void> {
    if (!env.APP_PRISMA_ENABLED) {
      return;
    }
    if (!env.DATABASE_URL) {
      throw new Error("DATABASE_URL is required when APP_PRISMA_ENABLED=true");
    }
    await this.hydrate();
    this.store.registerPersistenceSink(() => this.flush());
  }

  async onModuleDestroy(): Promise<void> {
    await this.store.waitForPersistence();
    await this.client?.$disconnect?.();
  }

  async hydrate(): Promise<void> {
    const prisma = await this.getClient();
    const [
      apiKeys,
      refreshTokens,
      ingestionJobs,
      sessions,
      tasks,
      steps,
      events,
      entities,
      relations,
      facts,
      memoryItems,
      memoryEvents,
      budgets,
      usageRows,
      datasets,
      cases,
      runs,
      results,
      chunks,
      harnessEvents,
      auditLogs,
      feedback,
      exposures,
      conversations,
      courses,
      schools,
      reservations
    ] = await Promise.all([
      prisma.apiKey.findMany(),
      prisma.refreshToken.findMany(),
      prisma.ingestionJob.findMany(),
      prisma.agentSessionState.findMany(),
      prisma.agentTask.findMany(),
      prisma.agentStep.findMany(),
      prisma.agentEvent.findMany(),
      prisma.kgEntity.findMany(),
      prisma.kgRelation.findMany(),
      prisma.kgFact.findMany(),
      prisma.memoryItem.findMany(),
      prisma.memoryEvent.findMany(),
      prisma.tenantBudget.findMany(),
      prisma.tenantUsageDaily.findMany(),
      prisma.evalDataset.findMany(),
      prisma.evalCase.findMany({ orderBy: [{ datasetId: "asc" }, { sortOrder: "asc" }] }),
      prisma.evalRun.findMany(),
      prisma.evalResult.findMany({ orderBy: { id: "asc" } }),
      prisma.knowledgeChunk.findMany(),
      prisma.harnessEvent.findMany(),
      prisma.auditLog.findMany({ orderBy: { id: "asc" } }),
      prisma.answerFeedback.findMany({ orderBy: { id: "asc" } }),
      prisma.modelAbExposure.findMany({ orderBy: { id: "asc" } }),
      prisma.conversation.findMany({ orderBy: { createTime: "asc" } }),
      prisma.course.findMany(),
      prisma.school.findMany(),
      prisma.courseReservation.findMany()
    ]);

    this.clearDurableState();
    for (const record of apiKeys) {
      this.store.apiKeys.set(record.keyHash, {
        keyHash: record.keyHash,
        keyName: record.keyName,
        roleName: record.roleName,
        tenantId: record.tenantId,
        enabled: record.enabled,
        lastUsedAt: isoOrUndefined(record.lastUsedAt),
        expiresAt: isoOrUndefined(record.expiresAt),
        revokedAt: isoOrUndefined(record.revokedAt),
        revokedReason: record.revokedReason ?? undefined,
        rotatedFromId: record.rotatedFromId?.toString(),
        createdAt: iso(record.createdAt),
        updatedAt: iso(record.updatedAt)
      });
    }
    for (const record of refreshTokens) {
      this.store.refreshTokens.set(record.tokenHash, {
        tokenHash: record.tokenHash,
        principal: record.principal,
        roles: splitRoles(record.roles),
        tenantId: record.tenantId,
        expiresAt: iso(record.expiresAt),
        revokedAt: isoOrUndefined(record.revokedAt),
        createdAt: iso(record.createdAt)
      });
    }
    for (const job of ingestionJobs) {
      const record = {
        jobId: job.jobId,
        tenantId: job.tenantId,
        chatId: job.chatId,
        sourceType: job.sourceType,
        sourceName: job.sourceName,
        filePath: job.filePath,
        idempotencyKey: job.idempotencyKey,
        contentHash: job.contentHash ?? "",
        rawText: job.rawText ?? "",
        status: job.status,
        traceId: job.traceId ?? "",
        attemptCount: job.attemptCount,
        maxRetries: job.maxRetries,
        errorMessage: job.errorMessage ?? undefined,
        nextRetryAt: isoOrUndefined(job.nextRetryAt),
        startedAt: isoOrUndefined(job.startedAt),
        finishedAt: isoOrUndefined(job.finishedAt),
        queueBackend: env.APP_INGESTION_QUEUE_BACKEND,
        createdAt: iso(job.createdAt),
        updatedAt: iso(job.updatedAt)
      };
      this.store.ingestionJobs.set(`${job.tenantId}:${job.jobId}`, record);
      this.store.idempotencyIndex.set(`${job.tenantId}:${job.idempotencyKey}`, job.jobId);
    }
    for (const row of sessions) {
      const payload = parseJsonRecord(row.sessionPayload);
      const session = {
        ...payload,
        id: row.sessionId,
        tenantId: row.tenantId,
        title: row.title,
        workspaceId: row.workspaceId,
        modelProfile: row.modelProfile,
        streaming: row.streaming,
        pinned: row.pinned,
        archived: row.archived,
        activeBranchId: row.activeBranchId ?? String(payload.activeBranchId ?? ""),
        branches: Array.isArray(payload.branches) ? payload.branches : [],
        updatedAt: row.updatedAt.getTime(),
        lockVersion: Number(row.lockVersion ?? 0)
      } as any;
      this.store.sessions.set(sessionKey(row.tenantId, row.sessionId), session);
    }
    for (const task of tasks) {
      this.store.workflowTasks.set(task.taskId, {
        taskId: task.taskId,
        tenantId: task.tenantId,
        type: task.type,
        status: task.status,
        userInput: task.userInput,
        finalOutput: task.finalOutput ?? undefined,
        modelProfile: task.modelProfile,
        chatId: task.chatId ?? undefined,
        sessionId: task.sessionId ?? undefined,
        createdAt: iso(task.createdAt),
        updatedAt: iso(task.updatedAt)
      });
    }
    for (const step of steps) {
      const values = this.store.workflowSteps.get(step.taskId) ?? [];
      values.push({
        stepId: step.stepId,
        taskId: step.taskId,
        agentName: step.agentName,
        status: step.status,
        stepOrder: step.stepOrder,
        thought: step.thought ?? undefined,
        action: step.action ?? undefined,
        actionInput: asRecord(step.actionInputJson),
        observation: step.observationJson,
        modelProfile: step.modelProfile ?? undefined,
        inputTokens: Number(step.inputTokens ?? 0),
        outputTokens: Number(step.outputTokens ?? 0),
        latencyMs: Number(step.latencyMs ?? 0),
        errorMessage: step.errorMessage ?? undefined,
        startedAt: iso(step.startedAt),
        endedAt: isoOrUndefined(step.endedAt)
      });
      this.store.workflowSteps.set(step.taskId, values);
    }
    for (const event of events) {
      const values = this.store.workflowEvents.get(event.taskId) ?? [];
      values.push({
        eventId: event.eventId,
        taskId: event.taskId,
        stepId: event.stepId ?? undefined,
        eventType: event.eventType,
        payload: event.payloadJson,
        createdAt: iso(event.createdAt)
      });
      this.store.workflowEvents.set(event.taskId, values);
    }
    this.store.graphEntities.push(...entities.map((item: any) => ({
      entityId: item.entityId,
      tenantId: item.tenantId,
      name: item.name,
      type: item.type,
      aliases: toStringArray(item.aliases),
      description: item.description ?? undefined,
      metadata: asRecord(item.metadataJson),
      createdAt: iso(item.createdAt),
      updatedAt: iso(item.updatedAt)
    })));
    this.store.graphRelations.push(...relations.map((item: any) => ({
      relationId: item.relationId,
      tenantId: item.tenantId,
      sourceEntityId: item.sourceEntityId,
      targetEntityId: item.targetEntityId,
      relationType: item.relationType,
      weight: item.weight,
      metadata: asRecord(item.metadataJson),
      createdAt: iso(item.createdAt),
      updatedAt: iso(item.createdAt)
    })));
    this.store.graphFacts.push(...facts.map((item: any) => ({
      factId: item.factId,
      tenantId: item.tenantId,
      subject: item.subject,
      predicate: item.predicate,
      object: item.object,
      confidence: item.confidence,
      source: item.source ?? undefined,
      metadata: asRecord(item.metadataJson),
      createdAt: iso(item.createdAt),
      updatedAt: iso(item.updatedAt)
    })));
    this.store.memoryItems.push(...memoryItems.map((item: any) => ({
      memoryId: item.memoryId,
      tenantId: item.tenantId,
      userId: item.userId ?? "anonymous",
      type: item.type,
      content: item.content,
      source: item.source ?? undefined,
      sourceTaskId: item.sourceTaskId ?? undefined,
      confidence: item.confidence,
      expiresAt: isoOrUndefined(item.expiresAt),
      createdAt: iso(item.createdAt),
      updatedAt: iso(item.updatedAt)
    })));
    for (const event of memoryEvents) {
      const values = this.store.memoryEvents.get(event.memoryId) ?? [];
      values.push({
        eventId: event.eventId,
        memoryId: event.memoryId,
        action: event.action,
        reason: event.reason ?? "",
        createdAt: iso(event.createdAt)
      });
      this.store.memoryEvents.set(event.memoryId, values);
    }
    for (const budget of budgets) {
      this.store.tenantBudgets.set(budget.tenantId, {
        tenantId: budget.tenantId,
        monthlyBudgetUsd: Number(budget.monthlyBudgetUsd),
        hardLimitEnabled: budget.hardLimitEnabled,
        createdAt: iso(budget.createdAt),
        updatedAt: iso(budget.updatedAt)
      });
    }
    this.committedBudgets = cloneBudgetMap(this.store.tenantBudgets);
    for (const usage of usageRows) {
      const usageDate = iso(usage.usageDate).slice(0, 10);
      this.store.tenantUsageDaily.set(tenantUsageKey(usage.tenantId, usageDate), {
        tenantId: usage.tenantId,
        usageDate,
        requestCount: Number(usage.requestCount),
        inputTokens: Number(usage.inputTokens),
        outputTokens: Number(usage.outputTokens),
        totalCostUsd: Number(usage.totalCostUsd),
        createdAt: iso(usage.createdAt),
        updatedAt: iso(usage.updatedAt)
      });
    }
    this.committedUsage = cloneUsageMap(this.store.tenantUsageDaily);
    for (const dataset of datasets) {
      const datasetCases = cases
        .filter((item: any) => item.tenantId === dataset.tenantId && item.datasetId === dataset.datasetId)
        .map((item: any) => ({
          caseId: item.caseId,
          category: item.category ?? undefined,
          chatId: item.chatId ?? undefined,
          question: item.questionText,
          expectedCitations: parseJsonArray(item.expectedCitationsJson),
          expectedKeywords: parseJsonArray(item.expectedKeywordsJson),
          forbiddenKeywords: parseJsonArray(item.forbiddenKeywordsJson)
        }));
      this.store.evalDatasets.set(dataset.datasetId, {
        datasetId: dataset.datasetId,
        tenantId: dataset.tenantId,
        name: dataset.name,
        description: dataset.description ?? undefined,
        baselineRunId: dataset.baselineRunId ?? undefined,
        cases: datasetCases,
        createdAt: iso(dataset.createdAt),
        updatedAt: iso(dataset.updatedAt)
      });
    }
    for (const run of runs) {
      const runResults = results
        .filter((item: any) => item.tenantId === run.tenantId && item.runId === run.runId)
        .map((item: any) => ({
          resultId: item.resultId,
          caseId: item.caseId,
          status: item.status,
          question: item.questionText,
          answer: item.answerText ?? "",
          citations: parseJsonArray(item.citationsJson),
          evidence: parseJsonArray(item.evidenceJson),
          retrievalHit: item.retrievalHit,
          citationCoverage: item.citationCoverage,
          keywordScore: item.keywordScore,
          answerFaithfulness: item.answerFaithfulness,
          score: item.score,
          latencyMs: Number(item.latencyMs),
          errorMessage: item.errorMessage ?? undefined
        }));
      this.store.evalRuns.set(run.runId, {
        runId: run.runId,
        datasetId: run.datasetId,
        tenantId: run.tenantId,
        status: run.status,
        modelProfile: run.modelProfile,
        metrics: {
          totalCases: run.totalCases,
          passedCases: run.passedCases,
          runScore: run.runScore,
          retrievalHitRate: run.retrievalHitRate,
          citationCoverageRate: run.citationCoverageRate,
          answerFaithfulnessScore: run.answerFaithfulnessScore,
          avgLatencyMs: run.avgLatencyMs,
          failureRate: run.failureRate
        },
        results: runResults,
        createdAt: iso(run.createdAt),
        startedAt: isoOrUndefined(run.startedAt),
        finishedAt: isoOrUndefined(run.finishedAt),
        errorMessage: run.errorMessage ?? undefined
      });
    }
    this.store.knowledgeChunks.push(...chunks.map((chunk: any) => ({
      chunkId: chunk.chunkId,
      tenantId: chunk.tenantId,
      chatId: chunk.chatId,
      jobId: chunk.jobId,
      fileName: chunk.fileName,
      sourceType: chunk.sourceType,
      chunkIndex: chunk.chunkIndex,
      content: chunk.content,
      tokenSet: tokenize(chunk.content),
      vector: toNumberArray(chunk.vectorJson, embeddingVector(chunk.content)),
      metadata: asRecord(chunk.metadataJson),
      createdAt: iso(chunk.createdAt)
    })));
    this.store.harnessEvents.push(...harnessEvents.map((item: any) => ({
      eventId: item.eventId,
      tenantId: item.tenantId,
      action: item.action,
      source: item.source,
      status: item.status,
      latencyMs: Number(item.latencyMs),
      payload: item.payloadJson,
      createdAt: iso(item.createdAt)
    })));
    this.store.auditLogs.push(...auditLogs.map((item: any) => ({
      id: Number(item.id),
      requestId: item.requestId ?? "",
      traceId: item.traceId ?? "",
      tenantId: item.tenantId,
      userIdentity: item.userIdentity ?? "anonymous",
      method: item.method,
      path: item.path,
      statusCode: item.statusCode,
      durationMs: Number(item.durationMs),
      chatId: item.chatId ?? "",
      jobId: item.jobId ?? "",
      extraPayload: item.extraPayload ?? "",
      createdAt: iso(item.createdAt)
    })));
    this.store.feedback.push(...feedback.map((item: any) => ({
      tenantId: item.tenantId,
      chatId: item.chatId,
      sessionId: item.sessionId ?? undefined,
      branchId: item.branchId ?? undefined,
      messageId: item.messageId ?? undefined,
      rating: item.rating,
      comment: item.comment ?? undefined,
      question: item.questionText ?? undefined,
      answer: item.answerText ?? undefined,
      createdAt: iso(item.createdAt)
    })));
    this.store.modelExposures.push(...exposures.map((item: any) => ({
      tenantId: item.tenantId,
      experimentKey: item.experimentKey,
      subjectKey: item.subjectKey,
      endpoint: item.endpoint,
      bucket: item.bucket,
      variant: item.variant,
      routedProfile: item.routedProfile,
      createdAt: iso(item.createdAt)
    })));
    for (const item of conversations) {
      const createdAt = iso(item.createTime);
      const role = String(item.type).toLowerCase();
      if (!["user", "assistant", "system"].includes(role)) {
        continue;
      }
      this.store.conversations.push({
        tenantId: item.tenantId,
        conversationId: item.conversationId,
        role: role as "user" | "assistant" | "system",
        content: item.message,
        createdAt
      });
      const separator = item.conversationId.indexOf("::");
      if (separator > 0) {
        const type = item.conversationId.slice(0, separator);
        const chatId = item.conversationId.slice(separator + 2);
        const key = historyKey(item.tenantId, type, chatId);
        const existing = this.store.historySessions.get(key);
        if (!existing || existing.updatedAt < createdAt) {
          this.store.historySessions.set(key, {
            tenantId: item.tenantId,
            type,
            chatId,
            conversationId: item.conversationId,
            updatedAt: createdAt
          });
        }
      }
    }
    this.store.courses.push(...courses.map((item: any) => ({
      id: item.id,
      name: item.name,
      edu: item.edu ?? undefined,
      type: item.type ?? undefined,
      price: item.price === null ? undefined : Number(item.price),
      duration: item.duration ?? undefined
    })));
    this.store.schools.push(...schools.map((item: any) => ({
      id: item.id,
      name: item.name,
      city: item.city ?? undefined
    })));
    this.store.courseReservations.push(...reservations.map((item: any) => ({
      id: item.id,
      course: item.course,
      studentName: item.studentName,
      contactInfo: item.contactInfo,
      school: item.school,
      remark: item.remark ?? undefined
    })));
    this.lastAuditIndex = this.store.auditLogs.length;
    this.lastFeedbackIndex = this.store.feedback.length;
    this.lastExposureIndex = this.store.modelExposures.length;
    this.lastConversationIndex = this.store.conversations.length;
  }

  async readiness(): Promise<{ enabled: boolean; database: "UP" | "DOWN"; persistence: "UP" | "DOWN" }> {
    if (!env.APP_PRISMA_ENABLED) {
      return { enabled: false, database: "DOWN", persistence: this.store.persistenceHealthy() ? "UP" : "DOWN" };
    }
    try {
      const prisma = await this.getClient();
      await prisma.$queryRawUnsafe("SELECT 1");
      return {
        enabled: true,
        database: "UP",
        persistence: this.store.persistenceHealthy() ? "UP" : "DOWN"
      };
    } catch {
      return { enabled: true, database: "DOWN", persistence: "DOWN" };
    }
  }

  async rotateRefreshToken(tokenHash: string, replacement: {
    tokenHash: string;
    principal: string;
    roles: string[];
    tenantId: string;
    expiresAt: string;
    createdAt: string;
  }): Promise<boolean> {
    if (!env.APP_PRISMA_ENABLED) {
      return true;
    }
    const prisma = await this.getClient();
    return prisma.$transaction(async (transaction: PrismaClientLike) => {
      const consumed = await transaction.refreshToken.updateMany({
        where: {
          tokenHash,
          revokedAt: null,
          expiresAt: { gt: new Date() }
        },
        data: { revokedAt: new Date() }
      });
      if (consumed.count !== 1) {
        return false;
      }
      await transaction.refreshToken.create({
        data: {
          tokenHash: replacement.tokenHash,
          principal: replacement.principal,
          roles: replacement.roles.join(","),
          tenantId: replacement.tenantId,
          expiresAt: new Date(replacement.expiresAt),
          createdAt: new Date(replacement.createdAt)
        }
      });
      return true;
    });
  }

  async flush(): Promise<void> {
    if (!env.APP_PRISMA_ENABLED || !env.DATABASE_URL) {
      return;
    }
    if (this.inFlight) {
      this.dirty = true;
      return;
    }
    this.inFlight = true;
    try {
      const prisma = await this.getClient();
      const appendOnlySnapshot = this.appendOnlySnapshot();
      const budgetSnapshot = cloneBudgetMap(this.store.tenantBudgets);
      const usageSnapshot = cloneUsageMap(this.store.tenantUsageDaily);
      // Session rows use conditional optimistic updates (V16), which require
      // the interactive transaction form instead of the array form below;
      // they flush in their own transaction ahead of the remaining entities.
      await this.flushSessions(prisma);
      const actions = [
        ...this.apiKeyActions(prisma),
        ...this.refreshTokenActions(prisma),
        ...this.ingestionActions(prisma),
        ...this.taskActions(prisma),
        ...this.graphActions(prisma),
        ...this.memoryActions(prisma, appendOnlySnapshot.deletedMemoryIds),
        ...this.costActions(prisma, budgetSnapshot, usageSnapshot),
        ...this.evaluationActions(prisma),
        ...this.knowledgeChunkActions(prisma),
        ...this.harnessEventActions(prisma),
        ...this.businessToolActions(prisma),
        ...this.appendOnlyActions(prisma, appendOnlySnapshot)
      ];
      if (actions.length > 0) {
        await prisma.$transaction(actions);
      }
      this.lastAuditIndex = appendOnlySnapshot.auditEnd;
      this.lastFeedbackIndex = appendOnlySnapshot.feedbackEnd;
      this.lastExposureIndex = appendOnlySnapshot.exposureEnd;
      this.lastConversationIndex = appendOnlySnapshot.conversationEnd;
      this.committedBudgets = budgetSnapshot;
      this.committedUsage = usageSnapshot;
      for (const memoryId of appendOnlySnapshot.deletedMemoryIds) {
        this.store.deletedMemoryIds.delete(memoryId);
      }
    } finally {
      this.inFlight = false;
      if (this.dirty) {
        this.dirty = false;
        await this.flush();
      }
    }
  }

  private clearDurableState(): void {
    this.store.apiKeys.clear();
    this.store.refreshTokens.clear();
    this.store.ingestionJobs.clear();
    this.store.idempotencyIndex.clear();
    this.store.knowledgeChunks.length = 0;
    this.store.sessions.clear();
    this.store.workflowTasks.clear();
    this.store.workflowSteps.clear();
    this.store.workflowEvents.clear();
    this.store.evalDatasets.clear();
    this.store.evalRuns.clear();
    this.store.trustedActions.clear();
    this.store.feedback.length = 0;
    this.store.auditLogs.length = 0;
    this.store.memoryItems.length = 0;
    this.store.memoryEvents.clear();
    this.store.deletedMemoryIds.clear();
    this.store.graphEntities.length = 0;
    this.store.graphRelations.length = 0;
    this.store.graphFacts.length = 0;
    this.store.historySessions.clear();
    this.store.conversations.length = 0;
    this.store.tenantBudgets.clear();
    this.store.tenantUsageDaily.clear();
    this.store.modelExposures.length = 0;
    this.store.harnessEvents.length = 0;
    this.store.courses.length = 0;
    this.store.schools.length = 0;
    this.store.courseReservations.length = 0;
  }

  private async getClient(): Promise<PrismaClientLike> {
    if (this.client) {
      return this.client;
    }
    const dynamicImport = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<{ PrismaClient: new () => PrismaClientLike }>;
    const module = await dynamicImport("@prisma/client");
    this.client = new module.PrismaClient();
    await this.client.$connect?.();
    return this.client;
  }

  private apiKeyActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [...this.store.apiKeys.values()].map((record) => prisma.apiKey.upsert({
      where: { keyHash: record.keyHash },
      update: {
        keyName: record.keyName,
        roleName: record.roleName,
        tenantId: record.tenantId,
        enabled: record.enabled,
        lastUsedAt: dateOrNull(record.lastUsedAt),
        expiresAt: dateOrNull(record.expiresAt),
        revokedAt: dateOrNull(record.revokedAt),
        revokedReason: record.revokedReason,
        updatedAt: dateOrNow(record.updatedAt)
      },
      create: {
        keyHash: record.keyHash,
        keyName: record.keyName,
        roleName: record.roleName,
        tenantId: record.tenantId,
        enabled: record.enabled,
        lastUsedAt: dateOrNull(record.lastUsedAt),
        expiresAt: dateOrNull(record.expiresAt),
        revokedAt: dateOrNull(record.revokedAt),
        revokedReason: record.revokedReason,
        createdAt: dateOrNow(record.createdAt),
        updatedAt: dateOrNow(record.updatedAt)
      }
    }));
  }

  private refreshTokenActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [...this.store.refreshTokens.values()].map((record) => {
      const tokenHash = record.tokenHash || sha256Hex(record.token ?? "");
      return prisma.refreshToken.upsert({
        where: { tokenHash },
        update: {
          principal: record.principal,
          roles: record.roles.join(","),
          tenantId: record.tenantId,
          expiresAt: dateOrNow(record.expiresAt),
          revokedAt: dateOrNull(record.revokedAt)
        },
        create: {
          tokenHash,
          principal: record.principal,
          roles: record.roles.join(","),
          tenantId: record.tenantId,
          expiresAt: dateOrNow(record.expiresAt),
          revokedAt: dateOrNull(record.revokedAt),
          createdAt: dateOrNow(record.createdAt)
        }
      });
    });
  }

  private ingestionActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [...this.store.ingestionJobs.values()].map((job) => prisma.ingestionJob.upsert({
      where: { jobId: job.jobId },
      update: ingestionPayload(job),
      create: ingestionPayload(job)
    }));
  }

  private async flushSessions(prisma: PrismaClientLike): Promise<void> {
    const sessions = [...this.store.sessions.values()];
    if (sessions.length === 0) {
      return;
    }
    await prisma.$transaction(async (transaction: PrismaClientLike) => {
      for (const session of sessions) {
        await this.upsertSessionState(transaction, session);
      }
    });
  }

  // Optimistic-locking mirror of the Java V16 remediation: the update is
  // conditional on the lock_version the store last observed; on conflict the
  // row is re-read and retried once instead of silently dropping either
  // writer's payload.
  private async upsertSessionState(prisma: PrismaClientLike, session: SessionState): Promise<unknown> {
    const key = { tenantId: session.tenantId ?? "public", sessionId: session.id };
    const payload = {
      title: session.title,
      workspaceId: session.workspaceId,
      modelProfile: session.modelProfile,
      streaming: session.streaming,
      pinned: session.pinned,
      archived: session.archived,
      activeBranchId: session.activeBranchId,
      sessionPayload: JSON.stringify(session),
      updatedAt: new Date(session.updatedAt)
    };
    const expectedVersion = BigInt(session.lockVersion ?? 0);
    const claimed = await prisma.agentSessionState.updateMany({
      where: { ...key, lockVersion: expectedVersion },
      data: { ...payload, lockVersion: { increment: 1 } }
    });
    if (claimed.count === 1) {
      session.lockVersion = Number(expectedVersion) + 1;
      return claimed;
    }
    const current = await prisma.agentSessionState.findUnique({ where: { tenantId_sessionId: key } });
    if (!current) {
      return prisma.agentSessionState.create({
        data: {
          ...key,
          ...payload,
          lockVersion: 0,
          createdAt: new Date(session.updatedAt)
        }
      });
    }
    const retried = await prisma.agentSessionState.updateMany({
      where: { ...key, lockVersion: current.lockVersion },
      data: { ...payload, lockVersion: { increment: 1 } }
    });
    if (retried.count !== 1) {
      throw new Error(`agent session state optimistic lock conflict: ${key.tenantId}/${key.sessionId}`);
    }
    session.lockVersion = Number(current.lockVersion) + 1;
    return retried;
  }

  private taskActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    const taskActions = [...this.store.workflowTasks.values()].map((task) => prisma.agentTask.upsert({
      where: { taskId: task.taskId },
      update: taskPayload(task),
      create: taskPayload(task)
    }));
    const stepActions = [...this.store.workflowSteps.values()].flat().map((step) => prisma.agentStep.upsert({
      where: { stepId: step.stepId },
      update: stepPayload(step),
      create: stepPayload(step)
    }));
    const eventActions = [...this.store.workflowEvents.values()].flat().map((event) => prisma.agentEvent.upsert({
      where: { eventId: event.eventId },
      update: { payloadJson: event.payload },
      create: {
        eventId: event.eventId,
        taskId: event.taskId,
        stepId: event.stepId,
        eventType: event.eventType,
        payloadJson: event.payload,
        createdAt: dateOrNow(event.createdAt)
      }
    }));
    return [...taskActions, ...stepActions, ...eventActions];
  }

  private graphActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [
      ...this.store.graphEntities.map((entity) => prisma.kgEntity.upsert({
        where: { entityId: entity.entityId },
        update: graphEntityPayload(entity),
        create: graphEntityPayload(entity)
      })),
      ...this.store.graphRelations.map((relation) => prisma.kgRelation.upsert({
        where: { relationId: relation.relationId },
        update: graphRelationPayload(relation),
        create: graphRelationPayload(relation)
      })),
      ...this.store.graphFacts.map((fact) => prisma.kgFact.upsert({
        where: { factId: fact.factId },
        update: graphFactPayload(fact),
        create: graphFactPayload(fact)
      }))
    ];
  }

  private memoryActions(prisma: PrismaClientLike, deletedMemoryIds: string[]): Array<Promise<unknown>> {
    const itemActions = this.store.memoryItems.map((item) => prisma.memoryItem.upsert({
      where: { memoryId: item.memoryId },
      update: memoryItemPayload(item),
      create: memoryItemPayload(item)
    }));
    const eventActions = [...this.store.memoryEvents.values()].flat().map((event) => prisma.memoryEvent.upsert({
      where: { eventId: event.eventId },
      update: { reason: event.reason },
      create: {
        eventId: event.eventId,
        memoryId: event.memoryId,
        action: event.action,
        reason: event.reason,
        createdAt: dateOrNow(event.createdAt)
      }
    }));
    return [
      ...(deletedMemoryIds.length > 0 ? [prisma.memoryItem.deleteMany({ where: { memoryId: { in: deletedMemoryIds } } })] : []),
      ...itemActions,
      ...eventActions
    ];
  }

  private costActions(
    prisma: PrismaClientLike,
    budgetSnapshot: Map<string, TenantBudgetRecord>,
    usageSnapshot: Map<string, TenantUsageDailyRecord>
  ): Array<Promise<unknown>> {
    const budgetActions = [...budgetSnapshot.values()]
      .filter((budget) => !sameBudget(budget, this.committedBudgets.get(budget.tenantId)))
      .map((budget) => prisma.tenantBudget.upsert({
        where: { tenantId: budget.tenantId },
        update: {
          monthlyBudgetUsd: budget.monthlyBudgetUsd,
          hardLimitEnabled: budget.hardLimitEnabled,
          updatedAt: dateOrNow(budget.updatedAt)
        },
        create: {
          tenantId: budget.tenantId,
          monthlyBudgetUsd: budget.monthlyBudgetUsd,
          hardLimitEnabled: budget.hardLimitEnabled,
          createdAt: dateOrNow(budget.createdAt),
          updatedAt: dateOrNow(budget.updatedAt)
        }
      }));
    const usageActions = [...usageSnapshot.entries()].flatMap(([key, usage]) => {
      const previous = this.committedUsage.get(key);
      const requestCount = Math.max(0, usage.requestCount - (previous?.requestCount ?? 0));
      const inputTokens = Math.max(0, usage.inputTokens - (previous?.inputTokens ?? 0));
      const outputTokens = Math.max(0, usage.outputTokens - (previous?.outputTokens ?? 0));
      const totalCostUsd = roundCostDelta(Math.max(0, usage.totalCostUsd - (previous?.totalCostUsd ?? 0)));
      if (requestCount === 0 && inputTokens === 0 && outputTokens === 0 && totalCostUsd === 0) {
        return [];
      }
      return [prisma.tenantUsageDaily.upsert({
        where: {
          tenantId_usageDate: {
            tenantId: usage.tenantId,
            usageDate: new Date(`${usage.usageDate}T00:00:00.000Z`)
          }
        },
        update: {
          requestCount: { increment: BigInt(requestCount) },
          inputTokens: { increment: BigInt(inputTokens) },
          outputTokens: { increment: BigInt(outputTokens) },
          totalCostUsd: { increment: totalCostUsd },
          updatedAt: dateOrNow(usage.updatedAt)
        },
        create: {
          tenantId: usage.tenantId,
          usageDate: new Date(`${usage.usageDate}T00:00:00.000Z`),
          requestCount: BigInt(requestCount),
          inputTokens: BigInt(inputTokens),
          outputTokens: BigInt(outputTokens),
          totalCostUsd,
          createdAt: dateOrNow(usage.createdAt),
          updatedAt: dateOrNow(usage.updatedAt)
        }
      })];
    });
    return [...budgetActions, ...usageActions];
  }

  private evaluationActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    const datasetActions = [...this.store.evalDatasets.values()].flatMap((dataset) => [
      prisma.evalDataset.upsert({
        where: { tenantId_datasetId: { tenantId: dataset.tenantId, datasetId: dataset.datasetId } },
        update: {
          name: dataset.name,
          description: dataset.description,
          baselineRunId: dataset.baselineRunId,
          updatedAt: dateOrNow(dataset.updatedAt)
        },
        create: {
          datasetId: dataset.datasetId,
          tenantId: dataset.tenantId,
          name: dataset.name,
          description: dataset.description,
          baselineRunId: dataset.baselineRunId,
          createdAt: dateOrNow(dataset.createdAt),
          updatedAt: dateOrNow(dataset.updatedAt)
        }
      }),
      ...dataset.cases.map((testCase, index) => {
        const caseId = String(testCase.caseId ?? `case-${index + 1}`);
        return prisma.evalCase.upsert({
          where: { tenantId_datasetId_caseId: { tenantId: dataset.tenantId, datasetId: dataset.datasetId, caseId } },
          update: evalCasePayload(dataset, testCase, caseId, index),
          create: evalCasePayload(dataset, testCase, caseId, index)
        });
      })
    ]);
    const runActions = [...this.store.evalRuns.values()].flatMap((run) => [
      prisma.evalRun.upsert({
        where: { tenantId_runId: { tenantId: run.tenantId, runId: run.runId } },
        update: evalRunPayload(run),
        create: evalRunPayload(run)
      }),
      ...run.results.map((result) => prisma.evalResult.upsert({
        where: { tenantId_resultId: { tenantId: run.tenantId, resultId: String(result.resultId) } },
        update: evalResultPayload(run, result),
        create: evalResultPayload(run, result)
      }))
    ]);
    return [...datasetActions, ...runActions];
  }

  private knowledgeChunkActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    if (!prisma.knowledgeChunk) {
      return [];
    }
    return this.store.knowledgeChunks.map((chunk) => prisma.knowledgeChunk.upsert({
      where: { chunkId: chunk.chunkId },
      update: {
        tenantId: chunk.tenantId,
        chatId: chunk.chatId,
        jobId: chunk.jobId,
        fileName: chunk.fileName,
        sourceType: chunk.sourceType,
        chunkIndex: chunk.chunkIndex,
        content: chunk.content,
        metadataJson: chunk.metadata,
        vectorJson: chunk.vector,
        updatedAt: new Date()
      },
      create: {
        chunkId: chunk.chunkId,
        tenantId: chunk.tenantId,
        chatId: chunk.chatId,
        jobId: chunk.jobId,
        fileName: chunk.fileName,
        sourceType: chunk.sourceType,
        chunkIndex: chunk.chunkIndex,
        content: chunk.content,
        metadataJson: chunk.metadata,
        vectorJson: chunk.vector,
        createdAt: dateOrNow(chunk.createdAt),
        updatedAt: new Date()
      }
    }));
  }

  private harnessEventActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    if (!prisma.harnessEvent) {
      return [];
    }
    return this.store.harnessEvents.map((event) => prisma.harnessEvent.upsert({
      where: { eventId: event.eventId },
      update: {
        tenantId: event.tenantId,
        action: event.action,
        source: event.source,
        status: event.status,
        latencyMs: BigInt(event.latencyMs),
        payloadJson: maskPayload(event.payload)
      },
      create: {
        eventId: event.eventId,
        tenantId: event.tenantId,
        action: event.action,
        source: event.source,
        status: event.status,
        latencyMs: BigInt(event.latencyMs),
        payloadJson: maskPayload(event.payload),
        createdAt: dateOrNow(event.createdAt)
      }
    }));
  }

  private businessToolActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    if (!prisma.course || !prisma.school || !prisma.courseReservation) {
      return [];
    }
    return [
      ...this.store.courses.map((course) => prisma.course.upsert({
        where: { id: course.id },
        update: coursePayload(course),
        create: coursePayload(course)
      })),
      ...this.store.schools.map((school) => prisma.school.upsert({
        where: { id: school.id },
        update: schoolPayload(school),
        create: schoolPayload(school)
      })),
      ...this.store.courseReservations.map((reservation) => prisma.courseReservation.upsert({
        where: { id: reservation.id },
        update: reservationPayload(reservation),
        create: reservationPayload(reservation)
      }))
    ];
  }

  private appendOnlySnapshot(): AppendOnlySnapshot {
    return {
      auditLogs: this.store.auditLogs.slice(this.lastAuditIndex),
      feedback: this.store.feedback.slice(this.lastFeedbackIndex),
      exposures: this.store.modelExposures.slice(this.lastExposureIndex),
      conversations: this.store.conversations.slice(this.lastConversationIndex),
      auditEnd: this.store.auditLogs.length,
      feedbackEnd: this.store.feedback.length,
      exposureEnd: this.store.modelExposures.length,
      conversationEnd: this.store.conversations.length,
      deletedMemoryIds: [...this.store.deletedMemoryIds]
    };
  }

  private appendOnlyActions(prisma: PrismaClientLike, snapshot: AppendOnlySnapshot): Array<Promise<unknown>> {
    return [
      ...snapshot.auditLogs.map((log) => prisma.auditLog.create({ data: auditPayload(log as Record<string, unknown>) })),
      ...snapshot.feedback.map((item) => prisma.answerFeedback.create({ data: feedbackPayload(item) })),
      ...snapshot.exposures.map((item) => prisma.modelAbExposure.create({ data: { ...item, createdAt: dateOrNow(item.createdAt) } })),
      ...snapshot.conversations.map((item) => {
        const id = conversationId(item);
        const data = {
          id,
          tenantId: item.tenantId,
          conversationId: item.conversationId,
          message: item.content,
          type: item.role.toUpperCase(),
          createTime: dateOrNow(item.createdAt)
        };
        return prisma.conversation.upsert({ where: { id }, update: data, create: data });
      })
    ];
  }
}

function dateOrNow(value: string | undefined): Date {
  return value ? new Date(value) : new Date();
}

function dateOrNull(value: string | undefined): Date | null {
  return value ? new Date(value) : null;
}

function ingestionPayload(job: any) {
  return {
    jobId: job.jobId,
    tenantId: job.tenantId,
    chatId: job.chatId,
    sourceType: job.sourceType,
    sourceName: job.sourceName,
    filePath: job.filePath,
    idempotencyKey: job.idempotencyKey,
    status: job.status,
    traceId: job.traceId,
    attemptCount: job.attemptCount,
    maxRetries: job.maxRetries,
    errorMessage: job.errorMessage,
    nextRetryAt: dateOrNull(job.nextRetryAt),
    contentHash: job.contentHash,
    rawText: job.rawText,
    startedAt: dateOrNull(job.startedAt),
    finishedAt: dateOrNull(job.finishedAt),
    createdAt: dateOrNow(job.createdAt),
    updatedAt: dateOrNow(job.updatedAt)
  };
}

function taskPayload(task: any) {
  return {
    taskId: task.taskId,
    tenantId: task.tenantId,
    type: task.type,
    status: task.status,
    userInput: task.userInput,
    finalOutput: task.finalOutput,
    modelProfile: task.modelProfile ?? "balanced",
    chatId: task.chatId,
    sessionId: task.sessionId,
    createdAt: dateOrNow(task.createdAt),
    updatedAt: dateOrNow(task.updatedAt)
  };
}

function stepPayload(step: any) {
  return {
    stepId: step.stepId,
    taskId: step.taskId,
    agentName: step.agentName,
    status: step.status,
    stepOrder: step.stepOrder,
    thought: step.thought,
    action: step.action,
    actionInputJson: step.actionInput,
    observationJson: step.observation,
    modelProfile: step.modelProfile,
    inputTokens: BigInt(step.inputTokens ?? 0),
    outputTokens: BigInt(step.outputTokens ?? 0),
    latencyMs: BigInt(step.latencyMs ?? 0),
    errorMessage: step.errorMessage,
    startedAt: dateOrNow(step.startedAt),
    endedAt: dateOrNull(step.endedAt)
  };
}

function graphEntityPayload(entity: any) {
  return {
    entityId: entity.entityId,
    tenantId: entity.tenantId,
    name: entity.name,
    type: entity.type,
    aliases: entity.aliases,
    description: entity.description,
    metadataJson: entity.metadata,
    createdAt: dateOrNow(entity.createdAt),
    updatedAt: dateOrNow(entity.updatedAt)
  };
}

function graphRelationPayload(relation: any) {
  return {
    relationId: relation.relationId,
    tenantId: relation.tenantId,
    sourceEntityId: relation.sourceEntityId,
    targetEntityId: relation.targetEntityId,
    relationType: relation.relationType,
    weight: relation.weight,
    metadataJson: relation.metadata,
    createdAt: dateOrNow(relation.createdAt)
  };
}

function graphFactPayload(fact: any) {
  return {
    factId: fact.factId,
    tenantId: fact.tenantId,
    subject: fact.subject,
    predicate: fact.predicate,
    object: fact.object,
    confidence: fact.confidence,
    source: fact.source,
    metadataJson: fact.metadata,
    createdAt: dateOrNow(fact.createdAt),
    updatedAt: dateOrNow(fact.updatedAt)
  };
}

function memoryItemPayload(item: any) {
  return {
    memoryId: item.memoryId,
    tenantId: item.tenantId,
    userId: item.userId,
    type: item.type,
    content: item.content,
    source: item.source,
    sourceTaskId: item.sourceTaskId,
    confidence: item.confidence,
    expiresAt: dateOrNull(item.expiresAt),
    createdAt: dateOrNow(item.createdAt),
    updatedAt: dateOrNow(item.updatedAt)
  };
}

function roundCostDelta(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function cloneBudgetMap(source: Map<string, TenantBudgetRecord>): Map<string, TenantBudgetRecord> {
  return new Map([...source].map(([key, value]) => [key, { ...value }]));
}

function cloneUsageMap(source: Map<string, TenantUsageDailyRecord>): Map<string, TenantUsageDailyRecord> {
  return new Map([...source].map(([key, value]) => [key, { ...value }]));
}

function sameBudget(left: TenantBudgetRecord, right: TenantBudgetRecord | undefined): boolean {
  return right !== undefined
    && left.monthlyBudgetUsd === right.monthlyBudgetUsd
    && left.hardLimitEnabled === right.hardLimitEnabled
    && left.updatedAt === right.updatedAt;
}

function evalCasePayload(dataset: any, testCase: Record<string, unknown>, caseId: string, index: number) {
  return {
    caseId,
    datasetId: dataset.datasetId,
    tenantId: dataset.tenantId,
    category: String(testCase.category ?? ""),
    chatId: String(testCase.chatId ?? ""),
    questionText: String(testCase.question ?? ""),
    expectedCitationsJson: JSON.stringify(testCase.expectedCitations ?? []),
    expectedKeywordsJson: JSON.stringify(testCase.expectedKeywords ?? []),
    forbiddenKeywordsJson: JSON.stringify(testCase.forbiddenKeywords ?? []),
    sortOrder: index,
    createdAt: dateOrNow(dataset.createdAt),
    updatedAt: dateOrNow(dataset.updatedAt)
  };
}

function evalRunPayload(run: any) {
  return {
    runId: run.runId,
    datasetId: run.datasetId,
    tenantId: run.tenantId,
    status: run.status,
    modelProfile: run.modelProfile,
    totalCases: run.metrics.totalCases ?? 0,
    passedCases: run.metrics.passedCases ?? 0,
    runScore: run.metrics.runScore ?? 0,
    retrievalHitRate: run.metrics.retrievalHitRate ?? 0,
    citationCoverageRate: run.metrics.citationCoverageRate ?? 0,
    answerFaithfulnessScore: run.metrics.answerFaithfulnessScore ?? 0,
    avgLatencyMs: run.metrics.avgLatencyMs ?? 0,
    failureRate: run.metrics.failureRate ?? 0,
    errorMessage: run.errorMessage,
    startedAt: dateOrNull(run.startedAt),
    finishedAt: dateOrNull(run.finishedAt),
    createdAt: dateOrNow(run.createdAt),
    updatedAt: dateOrNow(run.finishedAt ?? run.startedAt ?? run.createdAt)
  };
}

function evalResultPayload(run: any, result: Record<string, unknown>) {
  return {
    resultId: String(result.resultId),
    runId: run.runId,
    datasetId: run.datasetId,
    caseId: String(result.caseId),
    tenantId: run.tenantId,
    status: String(result.status),
    questionText: String(result.question),
    answerText: String(result.answer ?? ""),
    citationsJson: JSON.stringify(result.citations ?? []),
    evidenceJson: JSON.stringify(result.evidence ?? []),
    retrievalHit: Number(result.retrievalHit ?? 0),
    citationCoverage: Number(result.citationCoverage ?? 0),
    keywordScore: Number(result.keywordScore ?? 0),
    answerFaithfulness: Number(result.answerFaithfulness ?? 0),
    score: Number(result.score ?? 0),
    latencyMs: BigInt(Number(result.latencyMs ?? 0)),
    errorMessage: result.errorMessage ? String(result.errorMessage) : undefined,
    createdAt: dateOrNow(run.finishedAt ?? run.createdAt)
  };
}

function auditPayload(log: Record<string, unknown>) {
  return {
    requestId: String(log.requestId ?? ""),
    traceId: String(log.traceId ?? ""),
    tenantId: String(log.tenantId ?? "public"),
    userIdentity: String(log.userIdentity ?? "anonymous"),
    method: String(log.method ?? "GET"),
    path: String(log.path ?? "/"),
    statusCode: Number(log.statusCode ?? 0),
    durationMs: BigInt(Number(log.durationMs ?? 0)),
    chatId: String(log.chatId ?? ""),
    jobId: String(log.jobId ?? ""),
    extraPayload: String(log.extraPayload ?? ""),
    createdAt: dateOrNow(String(log.createdAt ?? ""))
  };
}

function feedbackPayload(item: Record<string, unknown>) {
  return {
    tenantId: String(item.tenantId ?? "public"),
    chatId: String(item.chatId ?? ""),
    sessionId: item.sessionId ? String(item.sessionId) : undefined,
    branchId: item.branchId ? String(item.branchId) : undefined,
    messageId: item.messageId ? String(item.messageId) : undefined,
    rating: Number(item.rating ?? 0),
    comment: item.comment ? String(item.comment).slice(0, 1024) : undefined,
    questionText: item.question ? String(item.question) : undefined,
    answerText: item.answer ? String(item.answer) : undefined,
    createdAt: dateOrNow(String(item.createdAt ?? ""))
  };
}

function coursePayload(course: any) {
  return {
    id: course.id,
    name: course.name,
    edu: course.edu,
    type: course.type,
    price: course.price === undefined ? undefined : BigInt(course.price),
    duration: course.duration
  };
}

function schoolPayload(school: any) {
  return {
    id: school.id,
    name: school.name,
    city: school.city
  };
}

function reservationPayload(reservation: any) {
  return {
    id: reservation.id,
    course: reservation.course,
    studentName: reservation.studentName,
    contactInfo: reservation.contactInfo,
    school: reservation.school,
    remark: reservation.remark
  };
}

function iso(value: Date): string {
  return value.toISOString();
}

function isoOrUndefined(value: Date | null | undefined): string | undefined {
  return value ? value.toISOString() : undefined;
}

function splitRoles(value: string): string[] {
  return value.split(",").map((role) => role.trim()).filter(Boolean);
}

function parseJsonRecord(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return asRecord(parsed);
  } catch {
    return {};
  }
}

function parseJsonArray(value: string | null | undefined): unknown[] {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function toNumberArray(value: unknown, fallback: number[]): number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number") ? value : fallback;
}

function conversationId(item: ConversationRecord): bigint {
  const digest = sha256Hex(`${item.tenantId}|${item.conversationId}|${item.role}|${item.createdAt}|${item.content}`);
  return BigInt(`0x${digest.slice(0, 15)}`);
}

function maskPayload(value: unknown): unknown {
  const text = JSON.stringify(value ?? {});
  return JSON.parse(text.replace(/(api[-_]?key|token|password)"\s*:\s*"[^"]*"/gi, '$1":"***"'));
}
