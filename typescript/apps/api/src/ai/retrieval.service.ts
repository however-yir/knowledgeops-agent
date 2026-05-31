import { Injectable } from "@nestjs/common";

import { cosineSimilarity, scoreByKeywordDensity, scoreByTokenOverlap, tokenize, truncateText } from "../common/text.js";
import { env } from "../config/env.js";
import { embeddingVector, KnowledgeChunk, PlatformStore } from "../platform/platform.store.js";

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
}

@Injectable()
export class RetrievalService {
  constructor(private readonly store: PlatformStore) {}

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
    deduped.sort((a, b) => b.finalScore - a.finalScore);
    return {
      documents: deduped.slice(0, topK),
      totalBeforeDedup: all.length,
      totalAfterDedup: deduped.length
    };
  }

  answer(query: string, tenantId: string, chatId: string) {
    const retrieval = this.hybridRetrieve(query, tenantId, chatId);
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
    const citations = chunks.map((chunk) => `source=${chunk.fileName}, chunk=${chunk.chunkIndex}`);
    return {
      answer: `根据当前知识库，最相关内容如下：\n${evidence.map((item, index) => `[${index + 1}] ${item}`).join("\n")}`,
      citations,
      evidence,
      retrievalStats: retrieval
    };
  }

  private vectorRetrieve(query: string, tenantId: string, chatId: string, topK: number): ScoredChunk[] {
    const queryVector = embeddingVector(query);
    return this.tenantChatChunks(tenantId, chatId)
      .map((chunk) => scored(chunk, cosineSimilarity(queryVector, chunk.vector), "vector"))
      .filter((chunk) => chunk.retrievalScore > 0)
      .sort((a, b) => b.retrievalScore - a.retrievalScore)
      .slice(0, topK);
  }

  private keywordRetrieve(query: string, tenantId: string, chatId: string, topK: number): ScoredChunk[] {
    return this.tenantChatChunks(tenantId, chatId)
      .map((chunk) => scored(chunk, Math.max(scoreByTokenOverlap(query, chunk.content), scoreByKeywordDensity(query, chunk.content)), "keyword"))
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
