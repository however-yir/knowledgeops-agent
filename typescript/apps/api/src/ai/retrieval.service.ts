import { Injectable, Optional } from "@nestjs/common";

import { cosineSimilarity, scoreByKeywordDensity, scoreByTokenOverlap, tokenize, truncateText } from "../common/text.js";
import { env } from "../config/env.js";
import { embeddingVector, KnowledgeChunk, PlatformStore } from "../platform/platform.store.js";
import { VectorClient } from "./vector.client.js";

export interface ScoredChunk extends KnowledgeChunk {
  retrievalScore: number;
  finalScore: number;
  source: "vector" | "keyword" | "graph" | "web";
  title: string;
  url?: string;
}

export interface HybridRetrievalResult {
  documents: ScoredChunk[];
  totalBeforeDedup: number;
  totalAfterDedup: number;
  stats: {
    vector: number;
    keyword: number;
    graph: number;
    web: number;
    judgedOut: number;
  };
}

@Injectable()
export class RetrievalService {
  constructor(
    private readonly store: PlatformStore,
    @Optional() private readonly vectorClient?: VectorClient
  ) {}

  addDocumentChunks(params: {
    tenantId: string;
    chatId: string;
    jobId: string;
    fileName: string;
    sourceType: string;
    text: string;
  }): KnowledgeChunk[] {
    const chunks = splitIntoChunks(params.text, env.RAG_CHUNK_SIZE).map((content, index) => ({
      chunkId: `${params.jobId}:${index}`,
      tenantId: params.tenantId,
      chatId: params.chatId,
      jobId: params.jobId,
      fileName: params.fileName,
      sourceType: params.sourceType,
      chunkIndex: index,
      content,
      tokenSet: tokenize(content),
      vector: embeddingVector(content),
      metadata: {
        tenant_id: params.tenantId,
        chat_id: params.chatId,
        file_name: params.fileName,
        chunk_index: index
      },
      createdAt: new Date().toISOString()
    }));
    this.store.knowledgeChunks.push(...chunks);
    void this.vectorClient?.upsertChunks(chunks).catch(() => undefined);
    return chunks;
  }

  retrieve(query: string, tenantId: string, chatId: string, topK = env.RAG_RETRIEVE_TOP_K): ScoredChunk[] {
    return this.hybridRetrieve(query, tenantId, chatId, topK).documents;
  }

  hybridRetrieve(query: string, tenantId: string, chatId: string, topK = env.RAG_RETRIEVE_TOP_K): HybridRetrievalResult {
    const vectorDocs = this.vectorRetrieve(query, tenantId, chatId, topK).map((doc) => applyWeight(doc, 0.4));
    const keywordDocs = this.keywordRetrieve(query, tenantId, chatId, topK).map((doc) => applyWeight(doc, 0.25));
    const graphDocs = this.graphRetrieve(query, tenantId, topK).map((doc) => applyWeight(doc, 0.2));
    const webDocs = this.webRetrieve(query, topK).map((doc) => applyWeight(doc, 0.15));
    const all = [...vectorDocs, ...keywordDocs, ...graphDocs, ...webDocs]
      .filter((doc) => doc.retrievalScore >= env.RAG_SIMILARITY_THRESHOLD);
    const deduped = deduplicate(all);
    const judged = judgeEvidence(query, rerank(query, deduped));
    return {
      documents: judged.slice(0, topK),
      totalBeforeDedup: all.length,
      totalAfterDedup: deduped.length,
      stats: {
        vector: vectorDocs.length,
        keyword: keywordDocs.length,
        graph: graphDocs.length,
        web: webDocs.length,
        judgedOut: deduped.length - judged.length
      }
    };
  }

  async answerAsync(query: string, tenantId: string, chatId: string) {
    const retrieval = await this.hybridRetrieveAsync(query, tenantId, chatId);
    return answerFromRetrieval(retrieval);
  }

  async hybridRetrieveAsync(query: string, tenantId: string, chatId: string, topK = env.RAG_RETRIEVE_TOP_K): Promise<HybridRetrievalResult> {
    const vectorDocs = (await this.vectorRetrieveAsync(query, tenantId, chatId, topK)).map((doc) => applyWeight(doc, 0.4));
    const keywordDocs = this.keywordRetrieve(query, tenantId, chatId, topK).map((doc) => applyWeight(doc, 0.25));
    const graphDocs = this.graphRetrieve(query, tenantId, topK).map((doc) => applyWeight(doc, 0.2));
    const webDocs = (await this.webRetrieveAsync(query, topK)).map((doc) => applyWeight(doc, 0.15));
    const all = [...vectorDocs, ...keywordDocs, ...graphDocs, ...webDocs]
      .filter((doc) => doc.retrievalScore >= env.RAG_SIMILARITY_THRESHOLD);
    const deduped = deduplicate(all);
    const reranked = await this.vectorClient?.rerank(query, deduped).catch(() => undefined) ?? rerank(query, deduped);
    const judged = await this.vectorClient?.judgeEvidence(query, reranked).catch(() => undefined) ?? judgeEvidence(query, reranked);
    return {
      documents: judged.slice(0, topK),
      totalBeforeDedup: all.length,
      totalAfterDedup: deduped.length,
      stats: {
        vector: vectorDocs.length,
        keyword: keywordDocs.length,
        graph: graphDocs.length,
        web: webDocs.length,
        judgedOut: deduped.length - judged.length
      }
    };
  }

  answer(query: string, tenantId: string, chatId: string) {
    const retrieval = this.hybridRetrieve(query, tenantId, chatId);
    return answerFromRetrieval(retrieval);
  }

  private vectorRetrieve(query: string, tenantId: string, chatId: string, topK: number): ScoredChunk[] {
    const queryVector = embeddingVector(query);
    return this.tenantChatChunks(tenantId, chatId)
      .map((chunk) => scored(chunk, cosineSimilarity(queryVector, chunk.vector), "vector"))
      .filter((chunk) => chunk.retrievalScore > 0)
      .sort((a, b) => b.retrievalScore - a.retrievalScore)
      .slice(0, topK);
  }

  private async vectorRetrieveAsync(query: string, tenantId: string, chatId: string, topK: number): Promise<ScoredChunk[]> {
    const external = await this.vectorClient?.searchPgVector(query, tenantId, chatId, topK).catch(() => undefined);
    if (external?.length) {
      return external.map((doc, index) => scored({
        chunkId: String(doc.chunkId ?? `pgvector:${index}`),
        tenantId: String(doc.tenantId ?? tenantId),
        chatId: String(doc.chatId ?? chatId),
        jobId: String(doc.jobId ?? "pgvector"),
        fileName: String(doc.fileName ?? doc.title ?? "pgvector"),
        sourceType: String(doc.sourceType ?? "VECTOR"),
        chunkIndex: Number(doc.chunkIndex ?? index),
        content: String(doc.content ?? ""),
        tokenSet: tokenize(String(doc.content ?? "")),
        vector: Array.isArray(doc.vector) ? doc.vector : embeddingVector(String(doc.content ?? "")),
        metadata: doc.metadata ?? {},
        createdAt: String(doc.createdAt ?? new Date().toISOString())
      }, Number(doc.retrievalScore ?? doc.finalScore ?? 0.5), "vector"));
    }
    return this.vectorRetrieve(query, tenantId, chatId, topK);
  }

  private keywordRetrieve(query: string, tenantId: string, chatId: string, topK: number): ScoredChunk[] {
    const corpus = this.tenantChatChunks(tenantId, chatId);
    return this.tenantChatChunks(tenantId, chatId)
      .map((chunk) => scored(chunk, Math.max(scoreByTokenOverlap(query, chunk.content), scoreByKeywordDensity(query, chunk.content), bm25Score(query, chunk, corpus)), "keyword"))
      .filter((chunk) => chunk.retrievalScore > 0)
      .sort((a, b) => b.retrievalScore - a.retrievalScore)
      .slice(0, topK);
  }

  private graphRetrieve(query: string, tenantId: string, topK: number): ScoredChunk[] {
    const queryTokens = tokenize(query);
    const entityDocs = this.store.graphEntities
      .filter((entity) => entity.tenantId === tenantId)
      .map((entity) => {
        const text = `${entity.name} ${entity.type} ${entity.description ?? ""} ${entity.aliases.join(" ")}`;
        const relationContext = this.store.graphRelations
          .filter((relation) => relation.tenantId === tenantId && (relation.sourceEntityId === entity.entityId || relation.targetEntityId === entity.entityId))
          .slice(0, 5)
          .map((relation) => `${relation.relationType}:${relation.sourceEntityId}->${relation.targetEntityId}`)
          .join("; ");
        return syntheticChunk({
          tenantId,
          content: `${text}${relationContext ? ` | ${relationContext}` : ""}`,
          chunkId: entity.entityId,
          fileName: `graph:${entity.name}`,
          score: tokenSetScore(queryTokens, text),
          source: "graph"
        });
      });
    const factDocs = this.store.graphFacts
      .filter((fact) => fact.tenantId === tenantId)
      .map((fact) => {
        const text = `${fact.subject} ${fact.predicate} ${fact.object}`;
        return syntheticChunk({
          tenantId,
          content: text,
          chunkId: fact.factId,
          fileName: `graph-fact:${fact.subject}`,
          score: tokenSetScore(queryTokens, text) * fact.confidence,
          source: "graph"
        });
      });
    return [...entityDocs, ...factDocs]
      .filter((chunk) => chunk.retrievalScore > 0)
      .sort((a, b) => b.retrievalScore - a.retrievalScore)
      .slice(0, topK);
  }

  private webRetrieve(query: string, topK: number): ScoredChunk[] {
    if (!env.APP_WEB_SEARCH_ENABLED || !env.APP_WEB_SEARCH_ENDPOINT) {
      return [];
    }
    const endpoint = `${env.APP_WEB_SEARCH_ENDPOINT.replace(/\/$/, "")}?q=${encodeURIComponent(query)}&format=json`;
    return [{
      ...syntheticChunk({
        tenantId: "public",
        content: `Web search configured at ${endpoint}. External retrieval is enabled for production runtime.`,
        chunkId: "web-configured",
        fileName: "web-search",
        score: 0.5,
        source: "web"
      }),
      url: endpoint
    }].slice(0, topK);
  }

  private async webRetrieveAsync(query: string, topK: number): Promise<ScoredChunk[]> {
    if (!env.APP_WEB_SEARCH_ENABLED || !env.APP_WEB_SEARCH_ENDPOINT) {
      return [];
    }
    const endpoint = `${env.APP_WEB_SEARCH_ENDPOINT.replace(/\/$/, "")}?q=${encodeURIComponent(query)}&format=json`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), env.APP_WEB_SEARCH_TIMEOUT_MS);
    try {
      const response = await fetch(endpoint, { signal: controller.signal });
      if (!response.ok) {
        return this.webRetrieve(query, topK);
      }
      const payload = await response.json().catch(() => undefined);
      const items = normalizeWebResults(payload, topK);
      return items.map((item, index) => ({
        ...syntheticChunk({
          tenantId: "public",
          content: `${item.title}\n${item.snippet}`,
          chunkId: `web:${index}:${item.url}`,
          fileName: item.title || "web-search",
          score: item.score,
          source: "web"
        }),
        url: item.url
      }));
    } catch {
      return this.webRetrieve(query, topK);
    } finally {
      clearTimeout(timeout);
    }
  }

  private tenantChatChunks(tenantId: string, chatId: string): KnowledgeChunk[] {
    return this.store.knowledgeChunks.filter((chunk) => chunk.tenantId === tenantId && (!chatId || chunk.chatId === chatId));
  }
}

function scored(chunk: KnowledgeChunk, score: number, source: ScoredChunk["source"]): ScoredChunk {
  return {
    ...chunk,
    retrievalScore: Number(score.toFixed(6)),
    finalScore: Number(score.toFixed(6)),
    source,
    title: chunk.fileName
  };
}

function syntheticChunk(params: {
  tenantId: string;
  content: string;
  chunkId: string;
  fileName: string;
  score: number;
  source: ScoredChunk["source"];
}): ScoredChunk {
  return scored({
    chunkId: params.chunkId,
    tenantId: params.tenantId,
    chatId: "",
    jobId: params.chunkId,
    fileName: params.fileName,
    sourceType: params.source,
    chunkIndex: 0,
    content: params.content,
    tokenSet: tokenize(params.content),
    vector: embeddingVector(params.content),
    metadata: {},
    createdAt: new Date().toISOString()
  }, params.score, params.source);
}

function applyWeight(chunk: ScoredChunk, weight: number): ScoredChunk {
  return { ...chunk, finalScore: Number((chunk.retrievalScore * weight).toFixed(6)) };
}

function deduplicate(chunks: ScoredChunk[]): ScoredChunk[] {
  const seen = new Map<string, ScoredChunk>();
  for (const chunk of chunks) {
    const fingerprint = chunk.content.replace(/\s+/g, " ").trim().slice(0, 200);
    const existing = seen.get(fingerprint);
    if (!existing || chunk.finalScore > existing.finalScore) {
      seen.set(fingerprint, chunk);
    }
  }
  return [...seen.values()];
}

function rerank(query: string, chunks: ScoredChunk[]): ScoredChunk[] {
  if (!env.RAG_RERANK_ENABLED) {
    return chunks.sort((a, b) => b.finalScore - a.finalScore);
  }
  const queryTokens = tokenize(query);
  return chunks
    .map((chunk) => {
      const titleScore = tokenSetScore(queryTokens, chunk.title);
      const sourceBoost = chunk.source === "graph" ? 0.03 : chunk.source === "web" ? 0.02 : 0;
      return {
        ...chunk,
        finalScore: roundScore(chunk.finalScore + titleScore * 0.08 + sourceBoost)
      };
    })
    .sort((a, b) => b.finalScore - a.finalScore);
}

function judgeEvidence(query: string, chunks: ScoredChunk[]): ScoredChunk[] {
  const queryTokens = tokenize(query);
  return chunks.filter((chunk) => {
    const topicality = Math.max(tokenSetScore(queryTokens, chunk.content), chunk.finalScore);
    return topicality >= env.RAG_EVIDENCE_JUDGE_MIN_SCORE;
  });
}

function answerFromRetrieval(retrieval: HybridRetrievalResult) {
  const chunks = retrieval.documents;
  if (chunks.length === 0) {
    return {
      answer: "没有在当前知识库中检索到可用内容。",
      citations: [],
      evidence: ["未检索到匹配文档，请先上传资料或调整检索词。"],
      retrievalStats: retrieval
    };
  }
  const evidence = chunks.map((chunk) => truncateText(chunk.content, 220));
  const citations = chunks.map((chunk) => citationText(chunk));
  const footer = citations.map((citation, index) => `[${index + 1}] ${citation}`).join("\n");
  return {
    answer: `根据当前知识库，最相关内容如下：\n${evidence.map((item, index) => `[${index + 1}] ${item}`).join("\n")}\n\n引用:\n${footer}`,
    citations,
    evidence,
    retrievalStats: retrieval
  };
}

function citationText(chunk: ScoredChunk): string {
  if (chunk.url) {
    return `source=${chunk.fileName}, url=${chunk.url}`;
  }
  return `source=${chunk.fileName}, chunk=${chunk.chunkIndex}`;
}

function bm25Score(query: string, chunk: KnowledgeChunk, corpus: KnowledgeChunk[]): number {
  const queryTokens = [...tokenize(query)];
  if (queryTokens.length === 0 || corpus.length === 0) {
    return 0;
  }
  const docTokens = [...tokenize(chunk.content)];
  const avgDocLength = corpus.reduce((sum, item) => sum + tokenize(item.content).size, 0) / Math.max(1, corpus.length);
  const k1 = 1.2;
  const b = 0.75;
  let score = 0;
  for (const token of queryTokens) {
    const termFrequency = docTokens.filter((item) => item === token).length;
    if (termFrequency === 0) {
      continue;
    }
    const docFrequency = corpus.filter((item) => item.tokenSet.has(token)).length;
    const idf = Math.log(1 + (corpus.length - docFrequency + 0.5) / (docFrequency + 0.5));
    const denominator = termFrequency + k1 * (1 - b + b * (docTokens.length / Math.max(1, avgDocLength)));
    score += idf * ((termFrequency * (k1 + 1)) / denominator);
  }
  return Math.min(1, score / Math.max(1, queryTokens.length));
}

function normalizeWebResults(payload: unknown, topK: number): Array<{ title: string; snippet: string; url: string; score: number }> {
  const rawItems = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as { results?: unknown[] } | undefined)?.results)
      ? (payload as { results: unknown[] }).results
      : [];
  return rawItems.slice(0, topK).map((item, index) => {
    const record = item && typeof item === "object" ? item as Record<string, unknown> : {};
    return {
      title: String(record.title ?? record.name ?? `web result ${index + 1}`),
      snippet: String(record.snippet ?? record.content ?? record.text ?? ""),
      url: String(record.url ?? record.link ?? ""),
      score: typeof record.score === "number" ? clampScore(record.score) : Math.max(0.15, 0.6 - index * 0.05)
    };
  }).filter((item) => item.snippet || item.title);
}

function splitIntoChunks(text: string, maxChunkSize: number): string[] {
  const normalized = text.replace(/\r/g, "").replace(/[ \t]+/g, " ").trim();
  if (!normalized) {
    return [];
  }
  const paragraphs = normalized.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
  const chunks: string[] = [];
  let current = "";
  for (const paragraph of paragraphs.length ? paragraphs : [normalized]) {
    if ((current + "\n\n" + paragraph).trim().length > maxChunkSize && current) {
      chunks.push(current.trim());
      current = paragraph;
    } else {
      current = [current, paragraph].filter(Boolean).join("\n\n");
    }
    while (current.length > maxChunkSize) {
      const next = current.slice(0, maxChunkSize).trim();
      if (next.length >= env.RAG_MIN_CHUNK_SIZE || chunks.length === 0) {
        chunks.push(next);
      }
      current = current.slice(maxChunkSize);
      if (chunks.length >= env.RAG_MAX_NUM_CHUNKS) {
        return chunks;
      }
    }
  }
  if (current.trim()) {
    chunks.push(current.trim());
  }
  return chunks.slice(0, env.RAG_MAX_NUM_CHUNKS);
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function roundScore(value: number): number {
  return Number(value.toFixed(6));
}

function tokenSetScore(queryTokens: Set<string>, text: string): number {
  if (queryTokens.size === 0) {
    return 0;
  }
  const tokens = tokenize(text);
  let hits = 0;
  for (const token of queryTokens) {
    if (tokens.has(token)) {
      hits += 1;
    }
  }
  return hits / queryTokens.size;
}
