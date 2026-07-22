import { afterEach, describe, expect, it, vi } from "vitest";

import { env } from "../config/env.js";
import type { ModelRouteDecision } from "../platform/model-router.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";

const original = {
  APP_LLM_ENABLED: env.APP_LLM_ENABLED,
  OPENAI_API_KEY: env.OPENAI_API_KEY,
  OPENAI_BASE_URL: env.OPENAI_BASE_URL,
  APP_LLM_FALLBACK_BASE_URL: env.APP_LLM_FALLBACK_BASE_URL,
  APP_LLM_FALLBACK_API_KEY: env.APP_LLM_FALLBACK_API_KEY,
  APP_LLM_FALLBACK_MODEL: env.APP_LLM_FALLBACK_MODEL,
  APP_LLM_MAX_RETRIES: env.APP_LLM_MAX_RETRIES
};

const route: ModelRouteDecision = {
  profile: "balanced",
  model: "primary-model",
  costTier: "balanced",
  fallbackApplied: false,
  reason: "test"
};

afterEach(() => {
  Object.assign(env, original);
  vi.unstubAllGlobals();
});

describe("OpenAiCompatibleClient", () => {
  it("parses fragmented SSE including CRLF split across chunks", async () => {
    configurePrimary();
    const first = JSON.stringify({ choices: [{ delta: { content: "Hel" } }] });
    const second = JSON.stringify({ choices: [{ delta: { content: "lo" } }] });
    const chunks = [
      `data: ${first}\r`,
      `\n\r\ndata: ${second}\r\n`,
      "\r\ndata: [DONE]\r\n\r\n"
    ];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(streamOf(chunks), {
      status: 200,
      headers: { "content-type": "text/event-stream" }
    })));

    const tokens: string[] = [];
    for await (const chunk of new OpenAiCompatibleClient().streamText({
      systemPrompt: "system",
      userPrompt: "hello",
      route
    })) {
      tokens.push(chunk.token);
    }

    expect(tokens).toEqual(["Hel", "lo"]);
  });

  it("switches to the configured provider after a primary failure", async () => {
    configurePrimary();
    env.APP_LLM_FALLBACK_BASE_URL = "https://fallback.example.test/v1";
    env.APP_LLM_FALLBACK_API_KEY = "fallback-key";
    env.APP_LLM_FALLBACK_MODEL = "fallback-model";
    env.APP_LLM_MAX_RETRIES = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      if (String(input).startsWith("https://primary.example.test")) {
        return new Response("primary unavailable", { status: 503 });
      }
      return Response.json({
        choices: [{ message: { content: "fallback answer" } }],
        usage: { prompt_tokens: 4, completion_tokens: 2 }
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await new OpenAiCompatibleClient().completeText({
      systemPrompt: "system",
      userPrompt: "question",
      route
    });

    expect(result).toMatchObject({
      answer: "fallback answer",
      model: "fallback-model",
      degraded: true,
      errorMessage: "primary unavailable"
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("propagates caller aborts without provider fallback", async () => {
    configurePrimary();
    env.APP_LLM_FALLBACK_BASE_URL = "https://fallback.example.test/v1";
    env.APP_LLM_FALLBACK_API_KEY = "fallback-key";
    env.APP_LLM_FALLBACK_MODEL = "fallback-model";
    const fetchMock = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason), { once: true });
    }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const pending = new OpenAiCompatibleClient().completeText({
      systemPrompt: "system",
      userPrompt: "question",
      route
    }, controller.signal);

    controller.abort(new DOMException("caller stopped", "AbortError"));

    await expect(pending).rejects.toThrow("caller stopped");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

function configurePrimary(): void {
  env.APP_LLM_ENABLED = true;
  env.OPENAI_API_KEY = "primary-key";
  env.OPENAI_BASE_URL = "https://primary.example.test/v1";
  env.APP_LLM_FALLBACK_BASE_URL = "";
  env.APP_LLM_FALLBACK_API_KEY = "";
  env.APP_LLM_FALLBACK_MODEL = "";
  env.APP_LLM_MAX_RETRIES = 0;
}

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    }
  });
}
