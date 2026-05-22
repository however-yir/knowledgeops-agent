export interface AuthTokenResponse {
  ok: number;
  msg: string;
  token?: string;
  refreshToken?: string;
  tenantId?: string;
  expiresInSeconds?: number;
  refreshWillExpireSoon?: boolean;
}

export interface ReactChatRequest {
  prompt: string;
  chatId: string;
  modelProfile?: string;
}

export interface ReactTraceStep {
  step: number;
  thought: string;
  action: string;
  actionInput?: Record<string, unknown>;
  observation?: unknown;
}

export interface ReactChatResponse {
  ok: number;
  msg: string;
  chatId: string;
  answer: string;
  citations?: string[];
  evidence?: string[];
  routeProfile?: string;
  routeReason?: string;
  routeCostTier?: string;
  experimentKey?: string;
  experimentVariant?: string;
  experimentBucket?: number;
  trace: ReactTraceStep[];
}

export interface ReactTokenEvent {
  token: string;
}

export interface ReactErrorEvent {
  message: string;
}

export type ReactStreamEvent = 'trace' | 'token' | 'done' | 'error';

export interface AuthContext {
  token?: string;
  apiKey?: string;
  tenantId?: string;
}

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  state?: 'pending' | 'streaming' | 'done' | 'error' | 'stopped';
  citations?: string[];
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

export interface BranchCompareRequest {
  sourceBranchId: string;
  targetBranchId: string;
}

export interface BranchCompareResult {
  sourceBranchId: string;
  targetBranchId: string;
  sourceMessageCount: number;
  targetMessageCount: number;
  commonMessageCount: number;
  sourceOnlyCount: number;
  targetOnlyCount: number;
  sourceOnlyPreview: string[];
  targetOnlyPreview: string[];
}

export interface BranchMergeRequest {
  sourceBranchId: string;
  targetBranchId: string;
  title?: string;
}

export interface BranchMergeResult {
  session: SessionState;
  mergedBranch: SessionBranch;
  mergedMessageCount: number;
}

export interface FeedbackRequest {
  chatId: string;
  sessionId?: string;
  branchId?: string;
  messageId?: string;
  rating: number;
  comment?: string;
  question?: string;
  answer: string;
}

export interface TenantCostSummary {
  tenantId: string;
  month: string;
  monthlyBudgetUsd: number;
  hardLimitEnabled: boolean;
  monthCostUsd: number;
  monthRequestCount: number;
  monthInputTokens: number;
  monthOutputTokens: number;
  todayCostUsd: number;
  todayRequestCount: number;
  budgetRemainingUsd: number;
  budgetExceeded: boolean;
}

export interface TenantBudgetUpdate {
  tenantId?: string;
  monthlyBudgetUsd?: number;
  hardLimitEnabled?: boolean;
}

export interface EvalCaseCreate {
  caseId?: string;
  category?: string;
  chatId?: string;
  question: string;
  expectedCitations?: string[];
  expectedKeywords?: string[];
  forbiddenKeywords?: string[];
}

export interface EvalDatasetCreate {
  name: string;
  description?: string;
  cases: EvalCaseCreate[];
}

export interface EvalDataset {
  datasetId: string;
  tenantId: string;
  name: string;
  description?: string;
  baselineRunId?: string;
  caseCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface EvalRunRequest {
  modelProfile?: string;
  chatIdPrefix?: string;
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

export interface EvalResult {
  resultId: string;
  caseId: string;
  status: string;
  question: string;
  answer: string;
  citations: string[];
  evidence: string[];
  retrievalHit: number;
  citationCoverage: number;
  keywordScore: number;
  answerFaithfulness: number;
  score: number;
  latencyMs: number;
  errorMessage?: string;
}

export interface EvalRun {
  runId: string;
  datasetId: string;
  tenantId: string;
  status: string;
  modelProfile: string;
  metrics: EvalMetricSummary;
  results: EvalResult[];
  errorMessage?: string;
  startedAt?: string;
  finishedAt?: string;
  createdAt: string;
}

export interface EvalComparison {
  dataset: EvalDataset;
  baseline?: EvalRun | null;
  current?: EvalRun | null;
}
