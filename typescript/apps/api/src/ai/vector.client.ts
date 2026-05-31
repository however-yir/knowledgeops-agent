import { Injectable } from "@nestjs/common";

import { env } from "../config/env.js";
import type { KnowledgeChunk } from "../platform/platform.store.js";
import type { ScoredChunk } from "./retrieval.service.js";

interface EmbeddingResponse {
  data?: Array<{ embedding?: number[] }>;
}

@Injectable()
export class VectorClient {
  async embed(text: string): Promise<number[] | undefined> {
    if (!env.APP_EMBEDDING_ENABLED || !env.OPENAI_API_KEY) {
      return undefined;
    }
    const response = await fetch(`${env.APP_EMBEDDING_BASE_URL.replace(/\/$/, "")}/embeddings`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${env.OPENAI_API_KEY}`,
        "content-type": "application/json"
      },
      body: JSON.stringify({ model: env.APP_EMBEDDING_MODEL, input: text })
    });
    if (!response.ok) {
      throw new Error(`embedding request failed with ${response.status}`);
    }
    const payload = await response.json() as EmbeddingResponse;
    return payload.data?.[0]?.embedding;
  }

  async upsertChunks(chunks: KnowledgeChunk[]): Promise<void> {
    if (env.APP_VECTOR_BACKEND !== "pgvector" || !env.APP_PGVECTOR_ENDPOINT) {
      return;
    }
    await fetch(`${env.APP_PGVECTOR_ENDPOINT.replace(/\/$/, "")}/upsert`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chunks: chunks.map((chunk) => ({
          chunkId: chunk.chunkId,
          tenantId: chunk.tenantId,
          chatId: chunk.chatId,
          content: chunk.content,
          metadata: chunk.metadata,
          vector: chunk.vector
        }))
      })
    });
  }

  async searchPgVector(query: string, tenantId: string, chatId: string, topK: number): Promise<Array<Partial<ScoredChunk>> | undefined> {
    if (env.APP_VECTOR_BACKEND !== "pgvector" || !env.APP_PGVECTOR_ENDPOINT) {
      return undefined;
    }
    const embedding = await this.embed(query).catch(() => undefined);
    const response = await fetch(`${env.APP_PGVECTOR_ENDPOINT.replace(/\/$/, "")}/search`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        query,
        embedding,
        tenantId,
        chatId,
        topK,
        similarityThreshold: env.RAG_SIMILARITY_THRESHOLD
      })
    });
    if (!response.ok) {
      return undefined;
    }
    const payload = await response.json().catch(() => undefined) as { documents?: Array<Partial<ScoredChunk>> } | undefined;
    return payload?.documents;
  }

  async rerank(query: string, chunks: ScoredChunk[]): Promise<ScoredChunk[] | undefined> {
    if (!env.RAG_RERANK_ENDPOINT) {
      return undefined;
    }
    const response = await fetch(env.RAG_RERANK_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, documents: chunks.map((chunk) => ({ id: chunk.chunkId, text: chunk.content, score: chunk.finalScore })) })
    });
    if (!response.ok) {
      return undefined;
    }
    const payload = await response.json().catch(() => undefined) as { scores?: Array<{ id: string; score: number }> } | undefined;
    const scores = new Map((payload?.scores ?? []).map((item) => [item.id, item.score]));
    return chunks
      .map((chunk) => ({ ...chunk, finalScore: scores.get(chunk.chunkId) ?? chunk.finalScore }))
      .sort((a, b) => b.finalScore - a.finalScore);
  }

  async judgeEvidence(query: string, chunks: ScoredChunk[]): Promise<ScoredChunk[] | undefined> {
    if (!env.RAG_EVIDENCE_JUDGE_ENDPOINT) {
      return undefined;
    }
    const response = await fetch(env.RAG_EVIDENCE_JUDGE_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, documents: chunks.map((chunk) => ({ id: chunk.chunkId, text: chunk.content, score: chunk.finalScore })) })
    });
    if (!response.ok) {
      return undefined;
    }
    const payload = await response.json().catch(() => undefined) as { acceptedIds?: string[] } | undefined;
    const accepted = new Set(payload?.acceptedIds ?? []);
    return accepted.size > 0 ? chunks.filter((chunk) => accepted.has(chunk.chunkId)) : undefined;
  }
}
