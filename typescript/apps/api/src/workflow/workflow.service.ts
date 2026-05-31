import { Injectable, OnModuleDestroy, OnModuleInit, Optional } from "@nestjs/common";

import { OpenAiCompatibleClient } from "../ai/llm.client.js";
import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { PlatformStore, WorkflowStep, WorkflowTask } from "../platform/platform.store.js";

type WorkflowState = "CREATED" | "PLANNING" | "SEARCHING" | "RETRIEVING" | "WRITING" | "DONE" | "FAILED";

@Injectable()
export class WorkflowService implements OnModuleInit, OnModuleDestroy {
  private timer: NodeJS.Timeout | undefined;
  private running = false;

  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly metrics: MetricsService,
    @Optional() private readonly llmClient?: OpenAiCompatibleClient,
    @Optional() private readonly modelRouter?: ModelRouterService
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
      taskId: newId("task"),
      tenantId: normalizeTenant(tenantId),
      type,
      status: "CREATED",
      userInput,
      modelProfile: modelProfile || "balanced",
      chatId,
      sessionId,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    this.store.workflowTasks.set(task.taskId, task);
    this.emitEvent(task.taskId, undefined, "STATE_CHANGED", { to: "CREATED" });
    this.store.persist();
    return task;
  }

  executeResearch(tenantId: string | undefined, topic: string, modelProfile?: string): WorkflowTask {
    const task = this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile, `research_${Date.now()}`);
    return this.runResearchTask(task);
  }

  async executeResearchAsync(tenantId: string | undefined, topic: string, modelProfile?: string): Promise<WorkflowTask> {
    const task = this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile, `research_${Date.now()}`);
    return this.runResearchTaskAsync(task);
  }

  enqueueResearch(tenantId: string | undefined, topic: string, modelProfile?: string): WorkflowTask {
    return this.createTask(tenantId, "DEEP_RESEARCH", topic, modelProfile, `research_${Date.now()}`);
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

  private async runResearchTaskAsync(task: WorkflowTask): Promise<WorkflowTask> {
    const started = Date.now();
    const topic = task.userInput;
    try {
      this.transition(task.taskId, "PLANNING");
      const planStep = this.startStep(task.taskId, "ResearchPlanner", 1, { topic });
      const subQuestions = await this.planResearchWithLlm(task, topic);
      this.completeStep(planStep.stepId, "COMPLETED", { subQuestions, strategy: "llm_hybrid_rag" }, { subQuestions }, "Plan research sub-questions with routed LLM fallback.", "plan", { topic });

      this.transition(task.taskId, "SEARCHING");
      const findings: string[] = [];
      let order = 2;
      for (const question of subQuestions) {
        this.transition(task.taskId, "RETRIEVING");
        const searchStep = this.startStep(task.taskId, "HybridRetriever", order, { question });
        const retrieval = await this.retrievalService.hybridRetrieveAsync(question, task.tenantId, task.chatId ?? "", 5);
        const finding = renderFinding(question, retrieval.documents.map((doc) => doc.content));
        findings.push(finding);
        this.completeStep(searchStep.stepId, "COMPLETED", { docsFound: retrieval.documents.length }, { finding }, "Retrieve evidence for sub-question.", "hybrid_retrieve", { question });
        order += 1;
      }

      this.transition(task.taskId, "WRITING");
      const writeStep = this.startStep(task.taskId, "ReportWriter", order, { topic });
      const report = await this.writeReportWithLlm(task, topic, findings);
      this.completeStep(writeStep.stepId, "COMPLETED", { reportLength: report.length }, report, "Write research report with routed LLM fallback.", "write_report", { topic });
      this.completeTask(task.taskId, "DONE", report);
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "DONE" });
      this.metrics.observe("agent_workflow_task_latency_ms", Date.now() - started, { type: task.type });
    } catch (error) {
      this.completeTask(task.taskId, "FAILED", error instanceof Error ? error.message : String(error));
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "FAILED" });
    }
    return this.getTask(task.taskId) ?? task;
  }

  private runResearchTask(task: WorkflowTask): WorkflowTask {
    const started = Date.now();
    const topic = task.userInput;
    try {
      this.transition(task.taskId, "PLANNING");
      const planStep = this.startStep(task.taskId, "ResearchPlanner", 1, { topic });
      const subQuestions = planResearch(topic);
      this.completeStep(planStep.stepId, "COMPLETED", { subQuestions, strategy: "hybrid_rag" }, { subQuestions }, "Split the topic into focused sub-questions.", "plan", { topic });

      this.transition(task.taskId, "SEARCHING");
      const findings: string[] = [];
      let order = 2;
      for (const question of subQuestions) {
        this.transition(task.taskId, "RETRIEVING");
        const searchStep = this.startStep(task.taskId, "HybridRetriever", order, { question });
        const retrieval = this.retrievalService.hybridRetrieve(question, task.tenantId, task.chatId ?? "", 5);
        const finding = renderFinding(question, retrieval.documents.map((doc) => doc.content));
        findings.push(finding);
        this.completeStep(searchStep.stepId, "COMPLETED", { docsFound: retrieval.documents.length }, { finding }, "Retrieve evidence for sub-question.", "hybrid_retrieve", { question });
        order += 1;
      }

      this.transition(task.taskId, "WRITING");
      const writeStep = this.startStep(task.taskId, "ReportWriter", order, { topic });
      const report = renderReport(topic, findings);
      this.completeStep(writeStep.stepId, "COMPLETED", { reportLength: report.length }, report, "Write a concise research report.", "write_report", { topic });
      this.completeTask(task.taskId, "DONE", report);
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "DONE" });
      this.metrics.increment("agent_workflow_task_latency_ms_sum", { type: task.type }, Date.now() - started);
      this.metrics.observe("agent_workflow_task_latency_ms", Date.now() - started, { type: task.type });
    } catch (error) {
      this.completeTask(task.taskId, "FAILED", error instanceof Error ? error.message : String(error));
      this.metrics.increment("agent_workflow_task_count", { type: task.type, status: "FAILED" });
    }
    return this.getTask(task.taskId) ?? task;
  }

  startReactTask(tenantId: string | undefined, prompt: string, modelProfile?: string, chatId?: string, sessionId?: string): WorkflowTask {
    const task = this.createTask(tenantId, "REACT_CHAT", prompt, modelProfile, chatId, sessionId);
    this.transition(task.taskId, "PLANNING");
    const step = this.startStep(task.taskId, "ReactPlanner", 1, { prompt });
    this.completeStep(step.stepId, "COMPLETED", { action: "hybrid_retrieve" }, null, "Plan a RAG-backed ReAct response.", "hybrid_retrieve", { prompt });
    this.completeTask(task.taskId, "DONE", "ReAct chat response generated by AiService");
    return this.getTask(task.taskId) ?? task;
  }

  getTask(taskId: string) {
    const task = this.store.workflowTasks.get(taskId);
    if (!task) {
      return undefined;
    }
    return {
      ...task,
      steps: this.store.workflowSteps.get(taskId) ?? [],
      events: this.store.workflowEvents.get(taskId) ?? []
    };
  }

  listTasks(tenantId: string, page: number, pageSize: number) {
    const safePage = Math.max(page, 1);
    const safePageSize = Math.max(pageSize, 1);
    const start = (safePage - 1) * safePageSize;
    return [...this.store.workflowTasks.values()]
      .filter((task) => task.tenantId === normalizeTenant(tenantId))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(start, start + safePageSize)
      .map((task) => this.getTask(task.taskId) ?? task);
  }

  getEvents(taskId: string) {
    return this.store.workflowEvents.get(taskId) ?? [];
  }

  private transition(taskId: string, to: WorkflowState): void {
    const task = this.store.workflowTasks.get(taskId);
    if (!task) {
      return;
    }
    const from = task.status;
    task.status = to;
    task.updatedAt = nowIso();
    this.emitEvent(taskId, undefined, "STATE_CHANGED", { from, to });
  }

  private startStep(taskId: string, agentName: string, stepOrder: number, input: Record<string, unknown>): WorkflowStep {
    const step: WorkflowStep = {
      stepId: newId("step"),
      taskId,
      agentName,
      status: "RUNNING",
      stepOrder,
      actionInput: input,
      inputTokens: JSON.stringify(input).length,
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

  private completeStep(stepId: string, status: string, output: Record<string, unknown>, observation: unknown, thought?: string, action?: string, actionInput?: Record<string, unknown>): void {
    for (const [taskId, steps] of this.store.workflowSteps.entries()) {
      const step = steps.find((candidate) => candidate.stepId === stepId);
      if (!step) {
        continue;
      }
      step.status = status;
      step.thought = thought;
      step.action = action;
      step.actionInput = actionInput ?? step.actionInput;
      step.observation = observation ?? output;
      step.outputTokens = JSON.stringify(output).length;
      step.latencyMs = Math.max(1, Date.now() - Date.parse(step.startedAt));
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
    this.emitEvent(taskId, undefined, finalStatus === "FAILED" ? "TASK_FAILED" : "TASK_COMPLETED", { status: finalStatus });
    this.store.persist();
  }

  private emitEvent(taskId: string, stepId: string | undefined, eventType: string, payload: unknown): void {
    const events = this.store.workflowEvents.get(taskId) ?? [];
    events.push({
      eventId: newId("evt"),
      taskId,
      stepId,
      eventType,
      payload,
      createdAt: nowIso()
    });
    this.store.workflowEvents.set(taskId, events);
  }

  private async planResearchWithLlm(task: WorkflowTask, topic: string): Promise<string[]> {
    const route = this.modelRouter?.resolve(task.modelProfile, "research_planner", task.tenantId, task.taskId);
    if (!route || !this.llmClient) {
      return planResearch(topic);
    }
    const result = await this.llmClient.complete({
      prompt: `Create three focused research sub-questions for: ${topic}. Return one per line.`,
      route,
      groundedContext: [],
      memoryContext: []
    }).catch(() => undefined);
    const lines = result?.answer.split("\n").map((line) => line.replace(/^[-*\d.\s]+/, "").trim()).filter(Boolean).slice(0, 5);
    return lines?.length ? lines : planResearch(topic);
  }

  private async writeReportWithLlm(task: WorkflowTask, topic: string, findings: string[]): Promise<string> {
    const route = this.modelRouter?.resolve(task.modelProfile, "research_writer", task.tenantId, task.taskId);
    if (!route || !this.llmClient) {
      return renderReport(topic, findings);
    }
    const result = await this.llmClient.complete({
      prompt: `Write a concise research report for ${topic}. Use these findings:\n${findings.join("\n\n")}`,
      route,
      groundedContext: findings,
      memoryContext: []
    }).catch(() => undefined);
    return result?.answer.trim() || renderReport(topic, findings);
  }
}

function planResearch(topic: string): string[] {
  const clean = topic.trim() || "research topic";
  return [
    clean,
    `${clean} key evidence`,
    `${clean} risks and recommendations`
  ];
}

function renderFinding(question: string, docs: string[]): string {
  if (docs.length === 0) {
    return `## ${question}\n\n- No matching local evidence was found.`;
  }
  return `## ${question}\n\n${docs.slice(0, 5).map((doc) => `- ${doc.slice(0, 240)}`).join("\n")}`;
}

function renderReport(topic: string, findings: string[]): string {
  return [
    `# Research Report: ${topic}`,
    "",
    "## Findings",
    findings.join("\n\n"),
    "",
    "## Recommendation",
    "Use the cited local knowledge first; add external web retrieval only when the configured search backend is enabled."
  ].join("\n");
}
