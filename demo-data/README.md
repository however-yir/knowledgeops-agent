# Demo Data

This directory contains small, reviewable sample documents for local RAG validation.

| File | Purpose |
|---|---|
| `heat-safety-policy.txt` | Source text for the heat safety RAG scenario. |
| `heat-safety-policy.pdf` | Upload this PDF through `/ingestion/upload/{chatId}` or the PDF endpoint. |

The sample content is intentionally non-sensitive and designed to exercise:

- PDF upload and async ingestion.
- Retrieval hit with citations.
- Evidence snippet display.
- Empty-result fallback behavior.
- Tenant isolation checks.
