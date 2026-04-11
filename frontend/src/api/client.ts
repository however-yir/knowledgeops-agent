import type {
  AuthContext,
  AuthTokenResponse,
  ReactChatRequest,
  ReactChatResponse,
  ReactStreamEvent
} from "../types/react";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

function resolveApi(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

function buildAuthHeaders(auth?: AuthContext): HeadersInit {
  const headers: Record<string, string> = {};
  if (auth?.token) {
    headers.Authorization = `Bearer ${auth.token}`;
  } else if (auth?.apiKey) {
    headers["X-API-Key"] = auth.apiKey;
  }
  if (auth?.tenantId) {
    headers["X-Tenant-ID"] = auth.tenantId;
  }
  return headers;
}

async function parseJsonSafely<T>(response: Response): Promise<T | null> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

function formatHttpError(status: number, message: string): Error {
  return new Error(`HTTP ${status}: ${message || "request failed"}`);
}

export async function exchangeApiKey(apiKey: string, tenantId?: string): Promise<AuthTokenResponse> {
  const response = await fetch(resolveApi("/auth/token"), {
    method: "POST",
    headers: {
      "X-API-Key": apiKey,
      ...(tenantId ? { "X-Tenant-ID": tenantId } : {})
    }
  });
  const payload = await parseJsonSafely<AuthTokenResponse>(response);
  if (!response.ok || !payload || payload.ok !== 1) {
    throw formatHttpError(response.status, payload?.msg ?? "token exchange failed");
  }
  return payload;
}

export async function refreshJwt(refreshToken: string): Promise<AuthTokenResponse> {
  const response = await fetch(resolveApi("/auth/refresh"), {
    method: "POST",
    headers: {
      "X-Refresh-Token": refreshToken
    }
  });
  const payload = await parseJsonSafely<AuthTokenResponse>(response);
  if (!response.ok || !payload || payload.ok !== 1) {
    throw formatHttpError(response.status, payload?.msg ?? "refresh token failed");
  }
  return payload;
}

export async function reactChat(request: ReactChatRequest, auth?: AuthContext): Promise<ReactChatResponse> {
  const response = await fetch(resolveApi("/ai/react/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(auth)
    },
    body: JSON.stringify(request)
  });
  const payload = await parseJsonSafely<ReactChatResponse>(response);
  if (!response.ok || !payload || payload.ok !== 1) {
    throw formatHttpError(response.status, payload?.msg ?? "react chat failed");
  }
  return payload;
}

type StreamHandler = (event: ReactStreamEvent, payload: unknown) => void;

interface ParsedEvent {
  event: ReactStreamEvent;
  payload: unknown;
}

function parseSseChunk(rawChunk: string): ParsedEvent | null {
  const normalized = rawChunk.replace(/\r/g, "");
  const lines = normalized.split("\n");
  let eventName: ReactStreamEvent = "token";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line.trim()) {
      continue;
    }
    if (line.startsWith("event:")) {
      const parsed = line.slice("event:".length).trim();
      if (parsed === "trace" || parsed === "token" || parsed === "done" || parsed === "error") {
        eventName = parsed;
      }
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  const joined = dataLines.join("\n");
  try {
    return {
      event: eventName,
      payload: JSON.parse(joined)
    };
  } catch {
    return {
      event: eventName,
      payload: joined
    };
  }
}

function takeNextChunk(input: string): { chunk: string; rest: string } | null {
  const lf = input.indexOf("\n\n");
  const crlf = input.indexOf("\r\n\r\n");

  if (lf < 0 && crlf < 0) {
    return null;
  }

  let splitAt = lf;
  let separatorLength = 2;
  if (lf < 0 || (crlf >= 0 && crlf < lf)) {
    splitAt = crlf;
    separatorLength = 4;
  }

  return {
    chunk: input.slice(0, splitAt),
    rest: input.slice(splitAt + separatorLength)
  };
}

export async function streamReactChat(
  request: ReactChatRequest,
  auth: AuthContext | undefined,
  onEvent: StreamHandler
): Promise<void> {
  const response = await fetch(resolveApi("/ai/react/chat/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...buildAuthHeaders(auth)
    },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    const errPayload = await parseJsonSafely<{ msg?: string }>(response);
    throw formatHttpError(response.status, errPayload?.msg ?? "stream init failed");
  }
  if (!response.body) {
    throw new Error("SSE stream body is empty");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    let next = takeNextChunk(buffer);
    while (next) {
      const chunk = next.chunk;
      buffer = next.rest;
      const parsed = parseSseChunk(chunk);
      if (parsed) {
        onEvent(parsed.event, parsed.payload);
      }
      next = takeNextChunk(buffer);
    }
  }

  buffer += decoder.decode();

  if (buffer.trim()) {
    const parsed = parseSseChunk(buffer);
    if (parsed) {
      onEvent(parsed.event, parsed.payload);
    }
  }
}
