import { Injectable, OnModuleInit } from "@nestjs/common";

import { env } from "../config/env.js";
import { PlatformStore, sha256Hex } from "./platform.store.js";

type PrismaClientLike = Record<string, any> & {
  $connect?: () => Promise<void>;
  $transaction?: (actions: Array<Promise<unknown>>) => Promise<unknown>;
};

@Injectable()
export class PrismaPersistenceService implements OnModuleInit {
  private client: PrismaClientLike | undefined;
  private inFlight = false;
  private dirty = false;
  private lastAuditIndex = 0;
  private lastFeedbackIndex = 0;
  private lastExposureIndex = 0;

  constructor(private readonly store: PlatformStore) {}

  onModuleInit(): void {
    if (!env.APP_PRISMA_ENABLED) {
      return;
    }
    this.store.registerPersistenceSink(() => this.flush());
    void this.flush();
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
      const actions = [
        ...this.apiKeyActions(prisma),
        ...this.refreshTokenActions(prisma),
        ...this.ingestionActions(prisma),
        ...this.sessionActions(prisma),
        ...this.taskActions(prisma),
        ...this.graphActions(prisma),
        ...this.memoryActions(prisma),
        ...this.costActions(prisma),
        ...this.evaluationActions(prisma),
        ...this.knowledgeChunkActions(prisma),
        ...this.harnessEventActions(prisma),
        ...this.businessToolActions(prisma),
        ...this.appendOnlyActions(prisma)
      ];
      if (actions.length > 0) {
        await prisma.$transaction?.(actions);
      }
    } finally {
      this.inFlight = false;
      if (this.dirty) {
        this.dirty = false;
        await this.flush();
      }
    }
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

  private sessionActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [...this.store.sessions.values()].map((session) => prisma.agentSessionState.upsert({
      where: { tenantId_sessionId: { tenantId: "public", sessionId: session.id } },
      update: {
        title: session.title,
        workspaceId: session.workspaceId,
        modelProfile: session.modelProfile,
        streaming: session.streaming,
        pinned: session.pinned,
        archived: session.archived,
        activeBranchId: session.activeBranchId,
        sessionPayload: JSON.stringify(session),
        updatedAt: new Date(session.updatedAt)
      },
      create: {
        sessionId: session.id,
        tenantId: "public",
        title: session.title,
        workspaceId: session.workspaceId,
        modelProfile: session.modelProfile,
        streaming: session.streaming,
        pinned: session.pinned,
        archived: session.archived,
        activeBranchId: session.activeBranchId,
        sessionPayload: JSON.stringify(session),
        createdAt: new Date(session.updatedAt),
        updatedAt: new Date(session.updatedAt)
      }
    }));
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

  private memoryActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
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
    return [...itemActions, ...eventActions];
  }

  private costActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    return [
      ...[...this.store.tenantBudgets.values()].map((budget) => prisma.tenantBudget.upsert({
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
      })),
      ...[...this.store.tenantUsageDaily.values()].map((usage) => prisma.tenantUsageDaily.upsert({
        where: { tenantId_usageDate: { tenantId: usage.tenantId, usageDate: dateOrNow(usage.usageDate) } },
        update: usagePayload(usage),
        create: usagePayload(usage)
      }))
    ];
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
        action: event.action,
        source: event.source,
        status: event.status,
        latencyMs: BigInt(event.latencyMs),
        payloadJson: maskPayload(event.payload)
      },
      create: {
        eventId: event.eventId,
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

  private appendOnlyActions(prisma: PrismaClientLike): Array<Promise<unknown>> {
    const auditLogs = this.store.auditLogs.slice(this.lastAuditIndex);
    const feedback = this.store.feedback.slice(this.lastFeedbackIndex);
    const exposures = this.store.modelExposures.slice(this.lastExposureIndex);
    this.lastAuditIndex = this.store.auditLogs.length;
    this.lastFeedbackIndex = this.store.feedback.length;
    this.lastExposureIndex = this.store.modelExposures.length;
    return [
      ...auditLogs.map((log) => prisma.auditLog.create({ data: auditPayload(log as Record<string, unknown>) })),
      ...feedback.map((item) => prisma.answerFeedback.create({ data: feedbackPayload(item) })),
      ...exposures.map((item) => prisma.modelAbExposure.create({ data: { ...item, createdAt: dateOrNow(item.createdAt) } }))
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

function usagePayload(usage: any) {
  return {
    tenantId: usage.tenantId,
    usageDate: dateOrNow(usage.usageDate),
    requestCount: BigInt(usage.requestCount),
    inputTokens: BigInt(usage.inputTokens),
    outputTokens: BigInt(usage.outputTokens),
    totalCostUsd: usage.totalCostUsd,
    createdAt: dateOrNow(usage.createdAt),
    updatedAt: dateOrNow(usage.updatedAt)
  };
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

function maskPayload(value: unknown): unknown {
  const text = JSON.stringify(value ?? {});
  return JSON.parse(text.replace(/(api[-_]?key|token|password)"\s*:\s*"[^"]*"/gi, '$1":"***"'));
}
