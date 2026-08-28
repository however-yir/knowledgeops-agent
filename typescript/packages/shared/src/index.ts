export interface Result {
  ok: 0 | 1;
  msg: string;
  /** Envelope payload; Java types it as Object, TypeScript as unknown. */
  data?: unknown;
  code?: string;
  traceId?: string;
}

export interface ApiHealth {
  status: "UP" | "DOWN";
}

export interface AuthTokenResponse {
  ok: number;
  msg: string;
  token?: string | null;
  refreshToken?: string | null;
  tenantId?: string | null;
  expiresInSeconds?: number | null;
  refreshExpiresAt?: string | null;
  refreshWillExpireSoon?: boolean | null;
}

export interface ApiKeyIssueResponse {
  ok: number;
  msg: string;
  keyName?: string;
  tenantId?: string;
  rawApiKey?: string;
  expiresAt?: string;
}

export interface ChatRequest {
  chatId: string;
  prompt: string;
  modelProfile?: string;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd?: number;
}

export interface Citation {
  id: string;
  source: string;
  title: string;
  chunkId: string;
  snippet: string;
}

export interface IngestionJob {
  jobId: string;
  chatId: string;
  sourceName: string;
  status: "PENDING" | "QUEUED" | "RUNNING" | "PROCESSING" | "SUCCEEDED" | "COMPLETED" | "RETRY" | "FAILED" | "DLQ";
  attemptCount: number;
  maxRetries: number;
  errorMessage?: string;
  traceId?: string;
  queueBackend: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
}

export interface IngestionSubmitResponse {
  ok: number;
  msg: string;
  job: IngestionJob | null;
}

export interface ReactTraceStep {
  step: number;
  thoughtSummary: string;
  action: string;
  actionInput?: Record<string, unknown>;
  observation?: unknown;
}

export interface ReactChatRequest extends ChatRequest {
  sessionId?: string;
  branchId?: string;
  messageId?: string;
}

export interface ReactChatResponse {
  ok: number;
  msg: string;
  chatId: string;
  answer: string;
  model: string;
  usage: TokenUsage;
  traceId: string;
  /** True when the answer was produced without the primary LLM path (Java `fallback`). */
  fallback?: boolean;
  citations?: Citation[];
  evidence?: string[];
  retrievalStats?: unknown;
  routeProfile?: string;
  routeReason?: string;
  routeCostTier?: string;
  experimentKey?: string;
  experimentVariant?: string;
  experimentBucket?: number;
  trace: ReactTraceStep[];
}

export interface CitationItem {
  id: string;
  source: string;
  title: string;
  chunkId: string;
  snippet: string;
}

export interface EvidenceItem {
  content: string;
  source: string;
  chunk: number;
  score: number;
}

export interface RagAnswer {
  answer: string;
  citations: Citation[];
  evidence: string[];
  retrievalStats: unknown;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SessionMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  state?: "pending" | "streaming" | "done" | "error" | "stopped";
  citations?: Citation[];
  evidence?: string[];
  taskId?: string;
  traceId?: string;
  memorySnapshot?: Array<Record<string, unknown>>;
  workflowState?: Record<string, unknown>;
}

export interface SessionBranch {
  id: string;
  title: string;
  parentBranchId: string | null;
  parentMessageId: string | null;
  updatedAt: number;
  messages: SessionMessage[];
  traceSteps: ReactTraceStep[];
}

export interface SessionState {
  id: string;
  tenantId?: string;
  title: string;
  updatedAt: number;
  modelProfile: string;
  streaming: boolean;
  pinned: boolean;
  archived: boolean;
  workspaceId: string;
  activeBranchId: string;
  branches: SessionBranch[];
  /** Optimistic-lock version mirrored from agent_session_state.lock_version (V16). */
  lockVersion?: number;
}

export interface EvalMetricSummary {
  totalCases: number;
  passedCases: number;
  runScore: number;
  retrievalHitRate: number;
  citationCoverageRate: number;
  answerFaithfulnessScore: number;
  avgLatencyMs: number;
  failureRate: number;
}

export function ok(data: unknown): Result {
  return {
    ok: 1,
    msg: "ok",
    data
  };
}

export function fail(msg: string, code = "BAD_REQUEST", traceId?: string): Result {
  return {
    ok: 0,
    msg,
    code,
    traceId
  };
}
