# Evaluation Baseline Dataset

This directory contains the quantitative baseline for the KnowledgeOps Agent evaluation.

## Metrics

| Metric | Target | Current | How to measure |
|---|---|---|---|
| Route accuracy | ≥ 90% | — | `evaluation/baseline/route-ground-truth.json` vs. RouteAgent output |
| Retrieval hit rate | ≥ 80% | — | `evaluation/baseline/retrieval-queries.json` → top-k hits |
| Citation quality | ≥ 0.75 | — | LLM-as-judge score on citation relevance |

## Files

- `route-ground-truth.json` — 20 queries with expected agent targets
- `retrieval-queries.json` — 15 queries with expected document IDs
- `citation-quality-samples.json` — 10 query-response pairs with human quality labels

## Running

```bash
python3 scripts/run_regression.py \
  --dataset evaluation/baseline/route-ground-truth.json \
  --predictions evaluation/predictions.route.json \
  --threshold 0.70
```
