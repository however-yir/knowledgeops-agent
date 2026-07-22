import { Injectable } from "@nestjs/common";

export interface EvaluationCaseInput {
  expectedKeywords?: unknown;
  expectedCitations?: unknown;
  forbiddenKeywords?: unknown;
}

export interface CaseScores {
  retrievalHit: number;
  citationCoverage: number;
  keywordScore: number;
  answerFaithfulness: number;
  score: number;
}

@Injectable()
export class EvaluationScorer {
  scoreCase(
    evalCase: EvaluationCaseInput,
    answer: string,
    citations: string[],
    evidence: string[],
    failed: boolean
  ): CaseScores {
    const expectedKeywords = stringList(evalCase.expectedKeywords);
    const expectedCitations = stringList(evalCase.expectedCitations);
    const forbiddenKeywords = stringList(evalCase.forbiddenKeywords);
    const answerPool = `${nonBlankOrEmpty(answer)}\n${evidence.join("\n")}`.toLowerCase();
    const citationPool = citations.join("\n").toLowerCase();

    let keywordScore = expectedKeywords.length === 0
      ? (answer.trim() ? 1 : 0)
      : hitRate(expectedKeywords, answerPool);
    const citationCoverage = expectedCitations.length === 0
      ? 1
      : hitRate(expectedCitations, citationPool);
    const forbiddenHit = forbiddenKeywords
      .filter((keyword) => keyword.trim())
      .some((keyword) => answerPool.includes(keyword.toLowerCase()));
    const retrievalHit = expectedCitations.length === 0
      ? (citations.length > 0 || evidence.length > 0 || keywordScore > 0 ? 1 : 0)
      : (citationCoverage > 0 ? 1 : 0);
    let answerFaithfulness = failed ? 0 : scoreFaithfulness(answer, citations);

    if (forbiddenHit) {
      keywordScore = 0;
      answerFaithfulness = Math.min(answerFaithfulness, 0.2);
    }

    const score = round(
      0.30 * retrievalHit
      + 0.25 * citationCoverage
      + 0.25 * keywordScore
      + 0.20 * answerFaithfulness
    );
    return {
      retrievalHit: round(retrievalHit),
      citationCoverage: round(citationCoverage),
      keywordScore: round(keywordScore),
      answerFaithfulness: round(answerFaithfulness),
      score
    };
  }
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => typeof item === "string" ? item : "")
    : [];
}

function hitRate(expected: string[], actualLower: string): number {
  if (expected.length === 0) {
    return 1;
  }
  const hits = expected
    .filter((item) => item.trim())
    .filter((item) => actualLower.includes(item.toLowerCase()))
    .length;
  return round(hits / expected.length);
}

function scoreFaithfulness(answer: string, citations: string[]): number {
  if (!answer.trim()) {
    return 0;
  }
  if (citations.length === 0) {
    return 0.5;
  }
  let markers = 0;
  for (let index = 1; index <= citations.length; index += 1) {
    if (answer.includes(`[${index}]`)) {
      markers += 1;
    }
  }
  return round(Math.min(1, markers / citations.length));
}

function nonBlankOrEmpty(value: string): string {
  return value.trim() ? value : "";
}

export function roundEvaluation(value: number): number {
  return round(value);
}

function round(value: number): number {
  return Math.round(value * 10000) / 10000;
}
