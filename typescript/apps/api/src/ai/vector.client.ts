import { Injectable, OnModuleDestroy } from "@nestjs/common";
import { Pool } from "pg";
import { toSql } from "pgvector/pg";

import { env } from "../config/env.js";
import { embeddingVector, type KnowledgeChunk } from "../platform/platform.store.js";
import type { ScoredChunk } from "./retrieval.service.js";

interface EmbeddingResponse {
  data?: Array<{ embedding?: number[] }>;
}

interface VectorRow {
  chunk_id: string;
  tenant_id: string;
  chat_id: string;
  job_id: string;
  file_name: string;
  source_type: string;
  chunk_index: number;
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: Date | string;
  retrieval_score: number | string;
}

@Injectable()
export class VectorClient implements OnModuleDestroy {
  private pool: Pool | undefined;
  private initialized: Promise<void> | undefined;

  async onModuleDestroy(): Promise<void> {
    await this.pool?.end();
  }

  async embed(text: string, signal?: AbortSignal): Promise<number[] | undefined> {
    if (!env.APP_EMBEDDING_ENABLED) return undefined;
    if (!env.OPENAI_API_KEY) throw new Error("OPENAI_API_KEY is required when embeddings are enabled");
    const response = await fetch(`${env.APP_EMBEDDING_BASE_URL.replace(/\/$/, "")}/embeddings`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${env.OPENAI_API_KEY}`,
        "content-type": "application/json"
      },
      body: JSON.stringify({ model: env.APP_EMBEDDING_MODEL, input: text }),
      signal: AbortSignal.any([signal ?? new AbortController().signal, AbortSignal.timeout(env.APP_LLM_TIMEOUT_MS)])
    });
    if (!response.ok) throw new Error(`embedding request failed with ${response.status}`);
    const payload = await response.json() as EmbeddingResponse;
    const vector = payload.data?.[0]?.embedding;
    if (!vector?.length) throw new Error("embedding response is empty");
    this.assertDimensions(vector);
    return vector;
  }

  async upsertChunks(chunks: KnowledgeChunk[]): Promise<void> {
    if (env.APP_VECTOR_BACKEND !== "pgvector" || chunks.length === 0) return;
    const pool = await this.pgPool();
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      for (const chunk of chunks) {
        const vector = await this.embed(chunk.content) ?? embeddingVector(chunk.content, env.APP_PGVECTOR_DIMENSIONS);
        this.assertDimensions(vector);
        await client.query(
          `INSERT INTO ${this.table()} (
             chunk_id, tenant_id, chat_id, job_id, file_name, source_type,
             chunk_index, content, metadata, embedding, created_at
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::vector, $11)
           ON CONFLICT (chunk_id) DO UPDATE SET
             tenant_id = EXCLUDED.tenant_id,
             chat_id = EXCLUDED.chat_id,
             job_id = EXCLUDED.job_id,
             file_name = EXCLUDED.file_name,
             source_type = EXCLUDED.source_type,
             chunk_index = EXCLUDED.chunk_index,
             content = EXCLUDED.content,
             metadata = EXCLUDED.metadata,
             embedding = EXCLUDED.embedding,
             created_at = EXCLUDED.created_at`,
          [
            chunk.chunkId,
            chunk.tenantId,
            chunk.chatId,
            chunk.jobId,
            chunk.fileName,
            chunk.sourceType,
            chunk.chunkIndex,
            chunk.content,
            JSON.stringify(chunk.metadata),
            toSql(vector),
            chunk.createdAt
          ]
        );
      }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  }

  async searchPgVector(query: string, tenantId: string, chatId: string, topK: number): Promise<Array<Partial<ScoredChunk>> | undefined> {
    if (env.APP_VECTOR_BACKEND !== "pgvector") return undefined;
    const vector = await this.embed(query) ?? embeddingVector(query, env.APP_PGVECTOR_DIMENSIONS);
    this.assertDimensions(vector);
    const values: unknown[] = [tenantId, toSql(vector), env.RAG_SIMILARITY_THRESHOLD, Math.max(1, topK)];
    const chatFilter = chatId ? "AND chat_id = $5" : "";
    if (chatId) values.push(chatId);
    const result = await (await this.pgPool()).query<VectorRow>(
      `SELECT chunk_id, tenant_id, chat_id, job_id, file_name, source_type,
              chunk_index, content, metadata, created_at,
              1 - (embedding <=> $2::vector) AS retrieval_score
         FROM ${this.table()}
        WHERE tenant_id = $1
          AND 1 - (embedding <=> $2::vector) >= $3
          ${chatFilter}
        ORDER BY embedding <=> $2::vector, chunk_id
        LIMIT $4`,
      values
    );
    return result.rows.map((row) => ({
      chunkId: row.chunk_id,
      tenantId: row.tenant_id,
      chatId: row.chat_id,
      jobId: row.job_id,
      fileName: row.file_name,
      sourceType: row.source_type,
      chunkIndex: row.chunk_index,
      content: row.content,
      metadata: row.metadata ?? {},
      createdAt: row.created_at instanceof Date ? row.created_at.toISOString() : String(row.created_at),
      retrievalScore: Number(row.retrieval_score),
      finalScore: Number(row.retrieval_score)
    }));
  }

  async rerank(query: string, chunks: ScoredChunk[]): Promise<ScoredChunk[] | undefined> {
    if (!env.RAG_RERANK_ENDPOINT) return undefined;
    const response = await fetch(env.RAG_RERANK_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, documents: chunks.map((chunk) => ({ id: chunk.chunkId, text: chunk.content, score: chunk.finalScore })) }),
      signal: AbortSignal.timeout(env.APP_LLM_TIMEOUT_MS)
    });
    if (!response.ok) return undefined;
    const payload = await response.json().catch(() => undefined) as { scores?: Array<{ id: string; score: number }> } | undefined;
    const scores = new Map((payload?.scores ?? []).map((item) => [item.id, item.score]));
    return chunks
      .map((chunk) => ({ ...chunk, finalScore: scores.get(chunk.chunkId) ?? chunk.finalScore }))
      .sort((a, b) => b.finalScore - a.finalScore);
  }

  async judgeEvidence(query: string, chunks: ScoredChunk[]): Promise<ScoredChunk[] | undefined> {
    if (!env.RAG_EVIDENCE_JUDGE_ENDPOINT) return undefined;
    const response = await fetch(env.RAG_EVIDENCE_JUDGE_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, documents: chunks.map((chunk) => ({ id: chunk.chunkId, text: chunk.content, score: chunk.finalScore })) }),
      signal: AbortSignal.timeout(env.APP_LLM_TIMEOUT_MS)
    });
    if (!response.ok) return undefined;
    const payload = await response.json().catch(() => undefined) as { acceptedIds?: string[] } | undefined;
    const accepted = new Set(payload?.acceptedIds ?? []);
    return accepted.size > 0 ? chunks.filter((chunk) => accepted.has(chunk.chunkId)) : undefined;
  }

  private async pgPool(): Promise<Pool> {
    if (!env.APP_PGVECTOR_URL) throw new Error("APP_PGVECTOR_URL is required for pgvector backend");
    this.pool ??= new Pool({ connectionString: env.APP_PGVECTOR_URL });
    this.initialized ??= this.initialize(this.pool);
    await this.initialized;
    return this.pool;
  }

  private async initialize(pool: Pool): Promise<void> {
    if (!env.APP_PGVECTOR_INITIALIZE_SCHEMA) return;
    await pool.query("CREATE EXTENSION IF NOT EXISTS vector");
    await pool.query(`CREATE SCHEMA IF NOT EXISTS ${quoteIdentifier(env.APP_PGVECTOR_SCHEMA)}`);
    await pool.query(
      `CREATE TABLE IF NOT EXISTS ${this.table()} (
         chunk_id text PRIMARY KEY,
         tenant_id text NOT NULL,
         chat_id text NOT NULL,
         job_id text NOT NULL,
         file_name text NOT NULL,
         source_type text NOT NULL,
         chunk_index integer NOT NULL,
         content text NOT NULL,
         metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
         embedding vector(${env.APP_PGVECTOR_DIMENSIONS}) NOT NULL,
         created_at timestamptz NOT NULL
       )`
    );
    await pool.query(`CREATE INDEX IF NOT EXISTS ${quoteIdentifier(`${env.APP_PGVECTOR_TABLE}_tenant_chat_idx`)} ON ${this.table()} (tenant_id, chat_id)`);
  }

  private table(): string {
    return `${quoteIdentifier(env.APP_PGVECTOR_SCHEMA)}.${quoteIdentifier(env.APP_PGVECTOR_TABLE)}`;
  }

  private assertDimensions(vector: number[]): void {
    if (vector.length !== env.APP_PGVECTOR_DIMENSIONS) {
      throw new Error(`embedding dimensions ${vector.length} do not match APP_PGVECTOR_DIMENSIONS=${env.APP_PGVECTOR_DIMENSIONS}`);
    }
  }
}

function quoteIdentifier(value: string): string {
  return `"${value.replace(/"/g, "\"\"")}"`;
}
