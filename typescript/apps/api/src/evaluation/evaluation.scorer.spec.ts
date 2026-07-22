import { describe, expect, it } from "vitest";

import { EvaluationScorer } from "./evaluation.scorer.js";

describe("EvaluationScorer", () => {
  const scorer = new EvaluationScorer();

  it("matches the Java citation and keyword coverage vector", () => {
    const scores = scorer.scoreCase({
      expectedKeywords: ["高温", "风险"],
      expectedCitations: ["heat-policy"],
      forbiddenKeywords: ["编造"]
    }, "高温风险处置建议见引用 [1]", ["vector:heat-policy:chunk-1"], ["高温风险包括中暑、脱水与慢病加重。"], false);

    expect(scores).toEqual({
      retrievalHit: 1,
      citationCoverage: 1,
      keywordScore: 1,
      answerFaithfulness: 1,
      score: 1
    });
  });

  it("matches the Java forbidden-keyword penalty vector", () => {
    const scores = scorer.scoreCase({
      expectedKeywords: ["高温"],
      expectedCitations: [],
      forbiddenKeywords: ["编造"]
    }, "这里编造一个高温结论。", [], [], false);

    expect(scores.keywordScore).toBe(0);
    expect(scores.answerFaithfulness).toBeLessThanOrEqual(0.2);
    expect(scores.score).toBeLessThan(0.7);
  });
});
