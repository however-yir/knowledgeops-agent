export interface Result<T> {
  ok: 0 | 1;
  msg: string;
  data?: T;
  code?: string;
  traceId?: string;
}

export interface ApiHealth {
  status: "UP" | "DOWN";
}

export interface AuthTokenResponse {
  ok: number;
  msg: string;
  token?: string;
  refreshToken?: string;
  tenantId?: string;
  expiresInSeconds?: number;
  refreshWillExpireSoon?: boolean;
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

export type ReactChatRequest = ChatRequest;

export interface ReactChatResponse {
  ok: number;
  msg: string;
  chatId: string;
  answer: string;
  model: string;
  usage: TokenUsage;
  traceId: string;
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
  title: string;
  updatedAt: number;
  modelProfile: string;
  streaming: boolean;
  pinned: boolean;
  archived: boolean;
  workspaceId: string;
  activeBranchId: string;
  branches: SessionBranch[];
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

export function ok<T>(data: T): Result<T> {
  return {
    ok: 1,
    msg: "ok",
    data
  };
}

export function fail(msg: string, code = "BAD_REQUEST", traceId?: string): Result<never> {
  return {
    ok: 0,
    msg,
    code,
    traceId
  };
}
