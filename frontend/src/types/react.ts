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

export type ReactStreamEvent = "trace" | "token" | "done" | "error";

export interface AuthContext {
  token?: string;
  apiKey?: string;
  tenantId?: string;
}

export interface SessionMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  state?: "pending" | "streaming" | "done" | "error" | "stopped";
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
