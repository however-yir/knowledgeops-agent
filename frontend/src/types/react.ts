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
