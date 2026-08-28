import { randomUUID } from "node:crypto";

import { BadRequestException, Injectable, OnModuleDestroy, OnModuleInit, Optional } from "@nestjs/common";

import { OpenAiCompatibleClient } from "../ai/llm.client.js";
import { RetrievalService } from "../ai/retrieval.service.js";
import { nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { PlatformStore, WorkflowStep, WorkflowTask } from "../platform/platform.store.js";
import { SessionsService } from "../sessions/sessions.service.js";

type WorkflowState =
  | "CREATED"
  | "PLANNING"
  | "SEARCHING"
  | "RETRIEVING"
  | "JUDGING"
  | "REFLECTING"
  | "WRITING"
  | "DONE"
  | "NEED_MORE_EVIDENCE"
  | "FAILED";

export interface WorkflowTaskView {
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
  steps: WorkflowStep[];
  events: import("../platform/platform.store.js").WorkflowEvent[];
}

export interface ResearchResult {
  taskId: string;
  topic: string;
  report: string;
  status: string;
}

@Injectable()
export class WorkflowService implements OnModuleInit, OnModuleDestroy {
  private timer: NodeJS.Timeout | undefined;
  private running = false;

  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly metrics: MetricsService,
    @Optional() private readonly llmClient?: OpenAiCompatibleClient,
    @Optional() private readonly modelRouter?: ModelRouterService,
    @Optional() private readonly sessionsService?: SessionsService
  ) {}

  onModuleInit(): void {
    if (!env.APP_WORKFLOW_ASYNC_ENABLED) {
      return;
    }
    this.timer = setInterval(() => void this.processQueuedTasks(), env.APP_WORKFLOW_WORKER_INTERVAL_MS);
    this.timer.unref?.();
  }

  onModuleDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }

  createTask(tenantId: string | undefined, type: string, userInput: string, modelProfile?: string, chatId?: string, sessionId?: string): WorkflowTask {
    const task: WorkflowTask = {
      taskId: workflowId("task"),
      tenantId: normalizeTenant(tenantId),
      type,
      status: "CREATED",
      userInput,
      modelProfile: hasText(modelProfile) ? modelProfile : "balanced",
      chatId,
      sessionId,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    this.store.workflowTasks.set(task.taskId, task);
    this.transition(task.taskId, "PLANNING", "CREATED");
    this.store.persist();
    return task;
  }

  executeResearch(tenantId: string | undefined, topic: string, modelProfile?: string): WorkflowTask {
    return this.runResearchTask(this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile));
  }

  async executeResearchAsync(tenantId: string | undefined, topic: string, modelProfile?: string): Promise<WorkflowTask> {
    return this.runResearchTaskAsync(this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile), true);
  }

  enqueueResearch(tenantId: string | undefined, topic: string, modelProfile?: string): WorkflowTask {
    return this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile);
  }

  toResearchResult(task: WorkflowTask): ResearchResult {
    return {
      taskId: task.taskId,
      topic: task.userInput,
      report: task.status === "FAILED" ? `Research failed: ${task.finalOutput ?? ""}` : task.finalOutput ?? "",
      status: task.status
    };
  }

  async processQueuedTasks(): Promise<number> {
    if (this.running) {
      return 0;
    }
    this.running = true;
    try {
      const candidates = [...this.store.workflowTasks.values()]
        .filter((task) => task.type === "DEEP_RESEARCH" && !["DONE", "FAILED"].includes(task.status))
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
        .slice(0, 1);
      for (const task of candidates) {
        await this.runResearchTaskAsync(task);
      }
      return candidates.length;
    } finally {
      this.running = false;
    }
  }

  private async runResearchTaskAsync(task: WorkflowTask, rethrow = false): Promise<WorkflowTask> {
    const started = Date.now();
    const topic = task.userInput;
    try {
      this.transition(task.taskId, "SEARCHING", "PLANNING");
      const planStep = this.startStep(task.taskId, "ResearchPlanner", 1, { topic });
      const plan = await this.planResearchWithLlm(task, topic);
      this.completeStep(planStep.stepId, "COMPLETED", { subQuestions: plan.subQuestions, strategy: plan.strategy }, plan);

      this.transition(task.taskId, "RETRIEVING", "SEARCHING");
      const findings: string[] = [];
      let order = 2;
      for (const question of plan.subQuestions) {
        const searchStep = this.startStep(task.taskId, "RagResearchAgent", order, { subQuestion: question });
        const retrieval = await this.retrievalService.hybridRetrieveAsync(question, task.tenantId, `research_${task.taskId}`, 5);
        const finding = renderFinding(question, retrieval.documents);
        findings.push(finding);
        this.completeStep(searchStep.stepId, "COMPLETED", { docsFound: retrieval.documents.length }, { finding });
        order += 1;
      }

      this.transition(task.taskId, "WRITING", "RETRIEVING");
      const writeStep = this.startStep(task.taskId, "ReportWriter", order, { topic });
      const report = await this.writeReportWithLlm(task, topic, findings);
      this.completeStep(writeStep.stepId, "COMPLETED", { reportLength: report.length }, report);
      this.completeTask(task.taskId, "DONE", report);
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "DONE" });
      this.metrics.observe("agent_workflow_task_latency_ms", Date.now() - started, { type: task.type });
    } catch (error) {
      this.failTask(task.taskId, messageFrom(error));
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "FAILED" });
      // Synchronous research requests surface the failure to the caller
      // instead of a 200 OK with a FAILED record (f112ce7 mirror); the
      // background worker path keeps relying on the recorded task.
      if (rethrow) {
        throw error;
      }
    }
    return this.store.workflowTasks.get(task.taskId) ?? task;
  }

  private runResearchTask(task: WorkflowTask): WorkflowTask {
    const started = Date.now();
    const topic = task.userInput;
    try {
      this.transition(task.taskId, "SEARCHING", "PLANNING");
      const planStep = this.startStep(task.taskId, "ResearchPlanner", 1, { topic });
      const plan = fallbackPlan(topic);
      this.completeStep(planStep.stepId, "COMPLETED", { subQuestions: plan.subQuestions, strategy: plan.strategy }, plan);

      this.transition(task.taskId, "RETRIEVING", "SEARCHING");
      const findings: string[] = [];
      let order = 2;
      for (const question of plan.subQuestions) {
        const searchStep = this.startStep(task.taskId, "RagResearchAgent", order, { subQuestion: question });
        const retrieval = this.retrievalService.hybridRetrieve(question, task.tenantId, `research_${task.taskId}`, 5);
        const finding = renderFinding(question, retrieval.documents);
        findings.push(finding);
        this.completeStep(searchStep.stepId, "COMPLETED", { docsFound: retrieval.documents.length }, { finding });
        order += 1;
      }

      this.transition(task.taskId, "WRITING", "RETRIEVING");
      const writeStep = this.startStep(task.taskId, "ReportWriter", order, { topic });
      const report = renderReport(topic, findings);
      this.completeStep(writeStep.stepId, "COMPLETED", { reportLength: report.length }, report);
      this.completeTask(task.taskId, "DONE", report);
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "DONE" });
      this.metrics.observe("agent_workflow_task_latency_ms", Date.now() - started, { type: task.type });
    } catch (error) {
      this.failTask(task.taskId, messageFrom(error));
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "FAILED" });
    }
    return this.store.workflowTasks.get(task.taskId) ?? task;
  }

  startReactTask(
    tenantId: string | undefined,
    prompt: string,
    modelProfile?: string,
    chatId?: string,
    sessionId?: string,
    type: "REACT" | "REACT_STREAM" = "REACT"
  ): WorkflowTask {
    if (!hasText(prompt)) {
      throw new BadRequestException("prompt is required");
    }
    if (!hasText(chatId)) {
      throw new BadRequestException("chatId is required");
    }
    const task = this.createTask(tenantId, type, prompt, modelProfile, chatId, sessionId);
    const step = this.startStep(task.taskId, "planner", 1, { prompt });
    // Persist the prompt's estimated input tokens on step completion (mirror of
    // the Java 60a69da fix: the column existed but was never written).
    const estimatedInputTokens = Math.max(1, Math.ceil([...prompt].length / env.APP_COST_TOKEN_ESTIMATE_DIVISOR));
    this.completeStep(step.stepId, "COMPLETED", { action: "hybrid_retrieve" }, null, "Plan a RAG-backed ReAct response.", "hybrid_retrieve", { prompt }, estimatedInputTokens);
    return task;
  }

  completeReactTask(tenantId: string, taskId: string, finalOutput: string): WorkflowTask | undefined {
    const task = this.taskForTenant(tenantId, taskId);
    if (!task) {
      return undefined;
    }
    this.completeTask(taskId, "DONE", finalOutput);
    return task;
  }

  failReactTask(tenantId: string, taskId: string, error: unknown): WorkflowTask | undefined {
    const task = this.taskForTenant(tenantId, taskId);
    if (!task) {
      return undefined;
    }
    this.failTask(taskId, messageFrom(error));
    return task;
  }

  attachSessionSnapshot(
    tenantId: string,
    taskId: string,
    traceId: string | undefined,
    sessionId: string | undefined,
    branchId: string | undefined,
    messageId: string | undefined
  ): void {
    const task = this.taskForTenant(tenantId, taskId);
    if (!task || !this.sessionsService || !hasText(sessionId) || !hasText(branchId) || !hasText(messageId)) {
      return;
    }
    const state = this.getTask(tenantId, taskId);
    this.sessionsService.attachWorkflowSnapshot(
      task.tenantId,
      sessionId,
      branchId,
      messageId,
      taskId,
      traceId,
      [],
      state ? { taskId: state.taskId, type: state.type, status: state.status, steps: state.steps } : {}
    );
  }

  getTask(tenantId: string, taskId: string): WorkflowTaskView | undefined {
    const task = this.taskForTenant(tenantId, taskId);
    if (!task) {
      return undefined;
    }
    return {
      ...task,
      steps: [...(this.store.workflowSteps.get(taskId) ?? [])].sort((a, b) => a.stepOrder - b.stepOrder),
      events: [...(this.store.workflowEvents.get(taskId) ?? [])].sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    };
  }

  listTasks(tenantId: string, page: number, pageSize: number): WorkflowTaskView[] {
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const start = (safePage - 1) * safePageSize;
    return [...this.store.workflowTasks.values()]
      .filter((task) => task.tenantId === normalizeTenant(tenantId))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(start, start + safePageSize)
      .map((task) => ({
        ...task,
        steps: [...(this.store.workflowSteps.get(task.taskId) ?? [])].sort((a, b) => a.stepOrder - b.stepOrder),
        events: []
      }));
  }

  getEvents(tenantId: string, taskId: string) {
    return this.getTask(tenantId, taskId)?.events ?? [];
  }

  currentState(taskId: string): WorkflowState | undefined {
    const status = this.store.workflowTasks.get(taskId)?.status;
    return isWorkflowState(status) ? status : status ? "FAILED" : undefined;
  }

  private taskForTenant(tenantId: string | undefined, taskId: string): WorkflowTask | undefined {
    const task = this.store.workflowTasks.get(taskId);
    return task?.tenantId === normalizeTenant(tenantId) ? task : undefined;
  }

  private transition(taskId: string, to: WorkflowState, expectedFrom?: WorkflowState): void {
    const task = this.store.workflowTasks.get(taskId);
    if (!task) {
      return;
    }
    const from = isWorkflowState(task.status) ? task.status : "FAILED";
    // The state machine stays authoritative: refuse a transition that does
    // not start from the expected state and skip its event, mirroring the
    // Java AgentWorkflowEngine.transitionStatus hardening (f112ce7).
    if (expectedFrom && from !== expectedFrom) {
      return;
    }
    task.status = to;
    task.updatedAt = nowIso();
    this.emitEvent(taskId, undefined, "STATE_CHANGED", { from: expectedFrom ?? from, to });
  }

  private startStep(taskId: string, agentName: string, stepOrder: number, input: Record<string, unknown>): WorkflowStep {
    const step: WorkflowStep = {
      stepId: workflowId("step"),
      taskId,
      agentName,
      status: "RUNNING",
      stepOrder,
      actionInput: input,
      inputTokens: 0,
      outputTokens: 0,
      latencyMs: 0,
      startedAt: nowIso()
    };
    const steps = this.store.workflowSteps.get(taskId) ?? [];
    steps.push(step);
    this.store.workflowSteps.set(taskId, steps);
    this.emitEvent(taskId, step.stepId, "STEP_STARTED", { agentName, stepOrder });
    return step;
  }

  private completeStep(
    stepId: string,
    status: string,
    output: Record<string, unknown>,
    observation: unknown,
    thought?: string,
    action?: string,
    actionInput?: Record<string, unknown>,
    inputTokens?: number
  ): void {
    for (const [taskId, steps] of this.store.workflowSteps.entries()) {
      const step = steps.find((candidate) => candidate.stepId === stepId);
      if (!step) {
        continue;
      }
      step.status = status;
      step.thought = thought;
      step.action = action;
      step.actionInput = actionInput ?? step.actionInput;
      step.observation = observation;
      step.inputTokens = inputTokens ?? 0;
      step.outputTokens = 0;
      step.latencyMs = Math.max(0, Date.now() - Date.parse(step.startedAt));
      step.endedAt = nowIso();
      this.emitEvent(taskId, stepId, "STEP_COMPLETED", { status, latencyMs: step.latencyMs });
      return;
    }
  }

  private completeTask(taskId: string, finalStatus: WorkflowState, finalOutput: string): void {
    const task = this.store.workflowTasks.get(taskId);
    if (!task) {
      return;
    }
    task.status = finalStatus;
    task.finalOutput = finalOutput;
    task.updatedAt = nowIso();
    this.emitEvent(taskId, undefined, "TASK_COMPLETED", { status: finalStatus });
    this.store.persist();
  }

  private failTask(taskId: string, errorMessage: string): void {
    const task = this.store.workflowTasks.get(taskId);
    if (!task) {
      return;
    }
    task.status = "FAILED";
    task.finalOutput = errorMessage;
    task.updatedAt = nowIso();
    this.emitEvent(taskId, undefined, "TASK_FAILED", { error: errorMessage });
    this.store.persist();
  }

  private emitEvent(taskId: string, stepId: string | undefined, eventType: string, payload: Record<string, unknown>): void {
    const events = this.store.workflowEvents.get(taskId) ?? [];
    events.push({
      eventId: workflowId("evt"),
      taskId,
      stepId,
      eventType,
      payload,
      createdAt: nowIso()
    });
    this.store.workflowEvents.set(taskId, events);
  }

  private async planResearchWithLlm(task: WorkflowTask, topic: string): Promise<ResearchPlan> {
    const route = this.modelRouter?.resolve(task.modelProfile, "research", task.tenantId, topic);
    if (!route || !this.llmClient) {
      return fallbackPlan(topic);
    }
    const result = await this.llmClient.complete({
      prompt: `Decompose the following research topic into 3-5 sub-questions. Return JSON only with subQuestions, keywords, and strategy.\n\nTopic: ${topic}`,
      route,
      groundedContext: [],
      memoryContext: []
    }).catch(() => undefined);
    return parseResearchPlan(result?.answer, topic);
  }

  private async writeReportWithLlm(task: WorkflowTask, topic: string, findings: string[]): Promise<string> {
    const route = this.modelRouter?.resolve(task.modelProfile, "research", task.tenantId, topic);
    if (!route || !this.llmClient) {
      return renderReport(topic, findings);
    }
    const result = await this.llmClient.complete({
      prompt: `Write a comprehensive research report in Chinese. Structure: 1) Executive Summary 2) Key Findings 3) Detailed Analysis 4) Conclusions & Recommendations.\n\nTopic: ${topic}\n\nResearch Findings:\n${findings.join("\n\n")}`,
      route,
      groundedContext: findings,
      memoryContext: []
    }).catch(() => undefined);
    return result?.answer.trim() || renderReport(topic, findings);
  }
}

interface ResearchPlan {
  subQuestions: string[];
  keywords: string[];
  strategy: string;
}

function fallbackPlan(topic: string): ResearchPlan {
  const cleanTopic = topic.trim() || "research topic";
  return {
    subQuestions: [
      `${cleanTopic}的背景与范围是什么？`,
      `${cleanTopic}有哪些关键证据和主要发现？`,
      `${cleanTopic}存在哪些风险，应采取哪些建议？`
    ],
    keywords: [],
    strategy: "breadth_first"
  };
}

function parseResearchPlan(raw: string | undefined, topic: string): ResearchPlan {
  if (!hasText(raw)) {
    return fallbackPlan(topic);
  }
  try {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    const parsed = JSON.parse(start >= 0 && end > start ? raw.slice(start, end + 1) : "{}") as Record<string, unknown>;
    const subQuestions = toStrings(parsed.subQuestions).slice(0, 5);
    if (subQuestions.length < 3) {
      return fallbackPlan(topic);
    }
    return {
      subQuestions,
      keywords: toStrings(parsed.keywords),
      strategy: hasText(parsed.strategy) ? String(parsed.strategy) : "breadth_first"
    };
  } catch {
    return fallbackPlan(topic);
  }
}

function renderFinding(question: string, docs: Array<{ sourceType?: string; title?: string; fileName?: string; content: string }>): string {
  const lines = [`## ${question}`, ""];
  for (const doc of docs) {
    lines.push(`- [${doc.sourceType ?? ""}] ${doc.title ?? doc.fileName ?? ""}: ${doc.content.slice(0, 200)}`);
  }
  return lines.join("\n");
}

function renderReport(topic: string, findings: string[]): string {
  const evidence = findings.length > 0 ? findings.join("\n\n") : "未检索到可用证据。";
  return [
    `# ${topic}研究报告`,
    "",
    "## 1. 执行摘要",
    `本报告围绕${topic}进行结构化研究，并基于当前可用证据形成结论。`,
    "",
    "## 2. 关键发现",
    evidence,
    "",
    "## 3. 详细分析",
    evidence,
    "",
    "## 4. 结论与建议",
    "优先采用已验证的本地知识证据；仅在外部搜索后端已配置并启用时补充网络检索。"
  ].join("\n");
}

function toStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(hasText) : [];
}

function isWorkflowState(value: unknown): value is WorkflowState {
  return [
    "CREATED", "PLANNING", "SEARCHING", "RETRIEVING", "JUDGING", "REFLECTING",
    "WRITING", "DONE", "NEED_MORE_EVIDENCE", "FAILED"
  ].includes(String(value));
}

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function messageFrom(error: unknown): string {
  return error instanceof Error && hasText(error.message) ? error.message : "workflow failed";
}

function workflowId(prefix: "task" | "step" | "evt"): string {
  return `${prefix}-${randomUUID().replaceAll("-", "")}`;
}
