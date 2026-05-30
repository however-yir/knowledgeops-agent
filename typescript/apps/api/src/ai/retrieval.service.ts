import { Injectable } from "@nestjs/common";

import { scoreByTokenOverlap, tokenize, truncateText } from "../common/text.js";
import { env } from "../config/env.js";
import { KnowledgeChunk, PlatformStore } from "../platform/platform.store.js";

export interface ScoredChunk extends KnowledgeChunk {
  score: number;
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
      createdAt: new Date().toISOString()
    }));
    this.store.knowledgeChunks.push(...chunks);
    return chunks;
  }

  retrieve(query: string, tenantId: string, chatId: string, topK = env.RAG_RETRIEVE_TOP_K): ScoredChunk[] {
    return this.store.knowledgeChunks
      .filter((chunk) => chunk.tenantId === tenantId && chunk.chatId === chatId)
      .map((chunk) => ({
        ...chunk,
        score: scoreByTokenOverlap(query, chunk.content)
      }))
      .filter((chunk) => chunk.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  answer(query: string, tenantId: string, chatId: string) {
    const chunks = this.retrieve(query, tenantId, chatId);
    if (chunks.length === 0) {
      return {
        answer: "没有在当前知识库中检索到可用内容。",
        citations: [],
        evidence: ["未检索到匹配文档，请先上传资料或调整检索词。"]
      };
    }
    const evidence = chunks.map((chunk) => truncateText(chunk.content, 180));
    const citations = chunks.map((chunk) => `source=${chunk.fileName}, chunk=${chunk.chunkIndex}`);
    return {
      answer: `根据当前知识库，最相关内容如下：\n${evidence.map((item, index) => `[${index + 1}] ${item}`).join("\n")}`,
      citations,
      evidence
    };
  }
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
      chunks.push(current.slice(0, maxChunkSize).trim());
      current = current.slice(maxChunkSize);
    }
  }
  if (current.trim()) {
    chunks.push(current.trim());
  }
  return chunks;
}
