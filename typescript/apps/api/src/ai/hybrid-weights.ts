/**
 * Configurable per-source weights for hybrid retrieval — TypeScript mirror of
 * the Java `HybridWeights` record (#115). Each preset covers the vector,
 * keyword, graph, and web sources; weights are normalized to sum to 1.0
 * before fusion. Tuning tip: factual/definitional queries benefit from a
 * higher vector weight; exact-match/lookup queries from a higher keyword
 * weight.
 */
export interface HybridWeights {
  vectorWeight: number;
  keywordWeight: number;
  graphWeight: number;
  webWeight: number;
}

export function hybridWeights(vectorWeight: number, keywordWeight: number, graphWeight: number, webWeight: number): HybridWeights {
  return { vectorWeight, keywordWeight, graphWeight, webWeight };
}

export const HYBRID_WEIGHT_PRESETS = {
  DEFAULT: hybridWeights(0.4, 0.25, 0.2, 0.15),
  SEMANTIC: hybridWeights(0.55, 0.2, 0.15, 0.1),
  KEYWORD: hybridWeights(0.2, 0.5, 0.15, 0.15),
  BALANCED: hybridWeights(0.25, 0.25, 0.25, 0.25)
} as const;

export function normalizeHybridWeights(weights: HybridWeights): HybridWeights {
  const sum = weights.vectorWeight + weights.keywordWeight + weights.graphWeight + weights.webWeight;
  if (sum <= 0) return HYBRID_WEIGHT_PRESETS.BALANCED;
  if (Math.abs(sum - 1) < 1e-9) return weights;
  return hybridWeights(
    weights.vectorWeight / sum,
    weights.keywordWeight / sum,
    weights.graphWeight / sum,
    weights.webWeight / sum
  );
}
