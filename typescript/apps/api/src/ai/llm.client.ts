import { Injectable } from "@nestjs/common";

import { env } from "../config/env.js";
import type { ModelRouteDecision } from "../platform/model-router.service.js";

export interface GroundedGenerationInput {
  prompt: string;
  groundedContext: string[];
  memoryContext: string[];
  route: ModelRouteDecision;
  systemPrompt?: string;
  temperature?: number;
}

export interface TextGenerationInput {
  systemPrompt: string;
  userPrompt: string;
  route: ModelRouteDecision;
  temperature?: number;
}

export interface GroundedGenerationResult {
  answer: string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
  degraded: boolean;
  errorMessage?: string;
}

export interface GroundedStreamChunk {
  token: string;
  model: string;
  degraded: boolean;
}

interface ChatCompletionResponse {
  choices?: Array<{ message?: { content?: string }; delta?: { content?: string } }>;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
  error?: { message?: string };
}

interface Provider {
  name: "primary" | "fallback";
  baseUrl: string;
  apiKey: string;
  model: string;
}

@Injectable()
export class OpenAiCompatibleClient {
  async complete(input: GroundedGenerationInput, signal?: AbortSignal): Promise<GroundedGenerationResult | undefined> {
    return this.completeText({
      systemPrompt: input.systemPrompt ?? env.APP_LLM_SYSTEM_PROMPT,
      userPrompt: groundedPrompt(input),
      route: input.route,
      temperature: input.temperature
    }, signal);
  }

  async completeText(input: TextGenerationInput, signal?: AbortSignal): Promise<GroundedGenerationResult | undefined> {
    const providers = configuredProviders(input.route.model);
    if (providers.length === 0) return undefined;
    let primaryError: Error | undefined;
    for (const [index, provider] of providers.entries()) {
      try {
        const response = await requestJson<ChatCompletionResponse>(provider, completionBody(input, provider.model, false), signal);
        const answer = response.choices?.[0]?.message?.content?.trim();
        if (!answer) throw new Error(response.error?.message || "empty LLM response");
        return {
          answer,
          model: provider.model,
          inputTokens: response.usage?.prompt_tokens,
          outputTokens: response.usage?.completion_tokens,
          degraded: provider.name === "fallback",
          errorMessage: provider.name === "fallback" ? primaryError?.message : undefined
        };
      } catch (error) {
        const normalized = asError(error);
        if (signal?.aborted) throw abortError(signal);
        primaryError ??= normalized;
        if (index === providers.length - 1) throw normalized;
      }
    }
    throw primaryError ?? new Error("LLM request failed");
  }

  async *streamComplete(input: GroundedGenerationInput, signal?: AbortSignal): AsyncGenerator<GroundedStreamChunk> {
    yield* this.streamText({
      systemPrompt: input.systemPrompt ?? env.APP_LLM_SYSTEM_PROMPT,
      userPrompt: groundedPrompt(input),
      route: input.route,
      temperature: input.temperature
    }, signal);
  }

  async *streamText(input: TextGenerationInput, signal?: AbortSignal): AsyncGenerator<GroundedStreamChunk> {
    const providers = configuredProviders(input.route.model);
    if (providers.length === 0) return;
    let primaryError: Error | undefined;
    for (const [index, provider] of providers.entries()) {
      let emitted = false;
      try {
        const response = await requestStream(provider, completionBody(input, provider.model, true), signal);
        for await (const token of parseOpenAiSse(response.body!, signal)) {
          emitted = true;
          yield { token, model: provider.model, degraded: provider.name === "fallback" };
        }
        if (!emitted) throw new Error("empty LLM stream");
        return;
      } catch (error) {
        const normalized = asError(error);
        if (signal?.aborted) throw abortError(signal);
        if (emitted) throw normalized;
        primaryError ??= normalized;
        if (index === providers.length - 1) throw normalized;
      }
    }
    throw primaryError ?? new Error("LLM stream failed");
  }
}

function configuredProviders(routeModel: string): Provider[] {
  if (!env.APP_LLM_ENABLED) return [];
  const providers: Provider[] = [];
  if (env.OPENAI_API_KEY) {
    providers.push({ name: "primary", baseUrl: env.OPENAI_BASE_URL, apiKey: env.OPENAI_API_KEY, model: routeModel });
  }
  if (env.APP_LLM_FALLBACK_BASE_URL && env.APP_LLM_FALLBACK_API_KEY && env.APP_LLM_FALLBACK_MODEL) {
    providers.push({
      name: "fallback",
      baseUrl: env.APP_LLM_FALLBACK_BASE_URL,
      apiKey: env.APP_LLM_FALLBACK_API_KEY,
      model: env.APP_LLM_FALLBACK_MODEL
    });
  }
  return providers;
}

function completionBody(input: TextGenerationInput, model: string, stream: boolean): Record<string, unknown> {
  return {
    model,
    temperature: input.temperature ?? env.APP_LLM_TEMPERATURE,
    ...(stream ? { stream: true, stream_options: { include_usage: true } } : {}),
    messages: [
      { role: "system", content: input.systemPrompt },
      { role: "user", content: input.userPrompt }
    ]
  };
}

function groundedPrompt(input: GroundedGenerationInput): string {
  const evidence = input.groundedContext.length
    ? input.groundedContext.map((item, index) => `[${index + 1}] ${item}`).join("\n")
    : "No evidence retrieved.";
  const memory = input.memoryContext.length
    ? input.memoryContext.map((item, index) => `M${index + 1}. ${item}`).join("\n")
    : "No relevant memory.";
  return [
    `Question:\n${input.prompt}`,
    "",
    `Retrieved evidence:\n${evidence}`,
    "",
    `Relevant memory:\n${memory}`,
    "",
    "Write the final answer in the user's language. Include numbered citations when evidence is available."
  ].join("\n");
}

async function requestJson<T>(provider: Provider, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await retryingFetch(provider, body, signal);
  const payload = await response.json().catch(() => ({}));
  return payload as T;
}

async function requestStream(provider: Provider, body: unknown, signal?: AbortSignal): Promise<Response> {
  const response = await retryingFetch(provider, body, signal);
  if (!response.body) throw new Error("LLM stream response has no body");
  return response;
}

async function retryingFetch(provider: Provider, body: unknown, signal?: AbortSignal): Promise<Response> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= env.APP_LLM_MAX_RETRIES; attempt += 1) {
    if (signal?.aborted) throw abortError(signal);
    const timeoutSignal = AbortSignal.timeout(env.APP_LLM_TIMEOUT_MS);
    const requestSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
    try {
      const response = await fetch(`${provider.baseUrl.replace(/\/$/, "")}/chat/completions`, {
        method: "POST",
        headers: {
          "authorization": `Bearer ${provider.apiKey}`,
          "content-type": "application/json"
        },
        body: JSON.stringify(body),
        signal: requestSignal
      });
      if (response.ok) return response;
      const message = await response.text().catch(() => "");
      const error = new Error(message || `LLM request failed with ${response.status}`);
      if (!isRetryableStatus(response.status) || attempt === env.APP_LLM_MAX_RETRIES) throw error;
      await delay(retryDelayMs(response.headers.get("retry-after"), attempt), signal);
    } catch (error) {
      if (signal?.aborted) throw abortError(signal);
      lastError = asError(error);
      if (!isRetryableError(error) || attempt === env.APP_LLM_MAX_RETRIES) throw lastError;
      await delay(retryDelayMs(null, attempt), signal);
    }
  }
  throw lastError ?? new Error(`${provider.name} LLM request failed`);
}

async function* parseOpenAiSse(body: ReadableStream<Uint8Array>, signal?: AbortSignal): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) throw abortError(signal);
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const events = splitSseEvents(buffer, done);
      buffer = events.remainder;
      for (const event of events.complete) {
        const token = tokenFromSseEvent(event);
        if (token === null) return;
        if (token) yield token;
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

function splitSseEvents(buffer: string, flush: boolean): { complete: string[]; remainder: string } {
  const pendingCr = !flush && buffer.endsWith("\r");
  const stable = pendingCr ? buffer.slice(0, -1) : buffer;
  const normalized = stable.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const parts = normalized.split("\n\n");
  if (flush) return { complete: parts.filter(Boolean), remainder: "" };
  const remainder = `${parts.at(-1) ?? ""}${pendingCr ? "\r" : ""}`;
  return { complete: parts.slice(0, -1).filter(Boolean), remainder };
}

function tokenFromSseEvent(event: string): string | null {
  const data = event
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n")
    .trim();
  if (!data) return "";
  if (data === "[DONE]") return null;
  let payload: ChatCompletionResponse;
  try {
    payload = JSON.parse(data) as ChatCompletionResponse;
  } catch {
    throw new Error("invalid JSON in LLM SSE event");
  }
  if (payload.error?.message) throw new Error(payload.error.message);
  return payload.choices?.[0]?.delta?.content ?? "";
}

function isRetryableStatus(status: number): boolean {
  return [408, 409, 425, 429].includes(status) || status >= 500;
}

function isRetryableError(error: unknown): boolean {
  return error instanceof TypeError
    || (error instanceof DOMException && ["AbortError", "TimeoutError", "NetworkError"].includes(error.name));
}

function retryDelayMs(retryAfter: string | null, attempt: number): number {
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds)) return Math.min(10_000, Math.max(0, seconds * 1000));
    const date = Date.parse(retryAfter);
    if (Number.isFinite(date)) return Math.min(10_000, Math.max(0, date - Date.now()));
  }
  return Math.min(4_000, 250 * 2 ** attempt);
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError(signal));
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(abortError(signal));
    }, { once: true });
  });
}

function abortError(signal: AbortSignal): Error {
  return signal.reason instanceof Error ? signal.reason : new DOMException("The operation was aborted", "AbortError");
}

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}
