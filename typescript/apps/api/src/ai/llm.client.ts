import { Injectable } from "@nestjs/common";

import { env } from "../config/env.js";
import type { ModelRouteDecision } from "../platform/model-router.service.js";

export interface GroundedGenerationInput {
  prompt: string;
  groundedContext: string[];
  memoryContext: string[];
  route: ModelRouteDecision;
}

export interface GroundedGenerationResult {
  answer: string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
  degraded: boolean;
  errorMessage?: string;
}

interface ChatCompletionResponse {
  choices?: Array<{ message?: { content?: string }; delta?: { content?: string } }>;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  error?: { message?: string };
}

@Injectable()
export class OpenAiCompatibleClient {
  async complete(input: GroundedGenerationInput): Promise<GroundedGenerationResult | undefined> {
    if (!env.APP_LLM_ENABLED || !env.OPENAI_API_KEY) {
      return undefined;
    }
    const body = {
      model: input.route.model,
      temperature: env.APP_LLM_TEMPERATURE,
      messages: [
        {
          role: "system",
          content: [
            "You are KnowledgeOps Agent. Answer from the provided evidence first.",
            "If evidence is weak, say what is missing instead of inventing facts.",
            "Keep citations as [1], [2], ... when citing evidence."
          ].join(" ")
        },
        {
          role: "user",
          content: groundedPrompt(input)
        }
      ]
    };
    const response = await retryingRequest<ChatCompletionResponse>(
      `${env.OPENAI_BASE_URL.replace(/\/$/, "")}/chat/completions`,
      body,
      env.APP_LLM_MAX_RETRIES
    );
    const answer = response.choices?.[0]?.message?.content?.trim();
    if (!answer) {
      throw new Error(response.error?.message || "empty LLM response");
    }
    return {
      answer,
      model: input.route.model,
      inputTokens: response.usage?.prompt_tokens,
      outputTokens: response.usage?.completion_tokens,
      degraded: false
    };
  }
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
    "Write the final answer in the user's language. Include a short citation footer when evidence is available."
  ].join("\n");
}

async function retryingRequest<T>(url: string, body: unknown, retries: number): Promise<T> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), env.APP_LLM_TIMEOUT_MS);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "authorization": `Bearer ${env.OPENAI_API_KEY}`,
          "content-type": "application/json"
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });
      const json = await response.json().catch(() => ({}));
      if (!response.ok) {
        const retryable = response.status === 429 || response.status >= 500;
        const message = typeof json === "object" && json && "error" in json
          ? JSON.stringify((json as { error: unknown }).error)
          : `LLM request failed with ${response.status}`;
        if (retryable && attempt < retries) {
          await delay(250 * (attempt + 1));
          continue;
        }
        throw new Error(message);
      }
      return json as T;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (attempt < retries) {
        await delay(250 * (attempt + 1));
        continue;
      }
    } finally {
      clearTimeout(timeout);
    }
  }
  throw lastError ?? new Error("LLM request failed");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
