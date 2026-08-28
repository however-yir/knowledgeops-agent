package com.enterprise.iqk.retrieval;

/**
 * Configurable per-source weights for hybrid retrieval.
 */
public record HybridWeights(double vectorWeight, double keywordWeight,
                             double graphWeight, double webWeight) {

    public static final HybridWeights DEFAULT = new HybridWeights(0.40, 0.25, 0.20, 0.15);
    public static final HybridWeights SEMANTIC = new HybridWeights(0.55, 0.20, 0.15, 0.10);
    public static final HybridWeights KEYWORD = new HybridWeights(0.20, 0.50, 0.15, 0.15);
    public static final HybridWeights BALANCED = new HybridWeights(0.25, 0.25, 0.25, 0.25);

    public static HybridWeights of(double vector, double keyword, double graph, double web) {
        return new HybridWeights(vector, keyword, graph, web);
    }

    public static HybridWeights semantic() { return SEMANTIC; }
    public static HybridWeights keyword() { return KEYWORD; }
    public static HybridWeights balanced() { return BALANCED; }

    public HybridWeights normalize() {
        double sum = vectorWeight + keywordWeight + graphWeight + webWeight;
        if (sum <= 0) return BALANCED;
        if (Math.abs(sum - 1.0) < 1e-9) return this;
        return new HybridWeights(vectorWeight / sum, keywordWeight / sum, graphWeight / sum, webWeight / sum);
    }
}
