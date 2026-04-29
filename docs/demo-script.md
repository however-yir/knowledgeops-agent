# Reproducible Demo Script

This script is designed for a 5 to 8 minute local walkthrough. It proves that KnowledgeOps Agent is a deployable Spring AI RAG platform, not a single-endpoint demo.

## 1. Start the Stack

```bash
./scripts/demo.sh
```

Expected result:

- Frontend console: `http://localhost:8088`
- Backend API: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/swagger-ui/index.html`
- Smoke test prints `e2e chat flow success`

## 2. Prepare Headers

Use the seeded local API key from `.env.example` or the console authentication card.

```bash
export BASE_URL=http://localhost:8080
export API_KEY=<local-demo-api-key>
export TENANT_ID=tenant-acme
export CHAT_ID=heat-safety-demo
```

## 3. Upload the Demo PDF

```bash
curl -X POST "$BASE_URL/ingestion/upload/$CHAT_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID" \
  -H "X-Idempotency-Key: heat-safety-policy-v1" \
  -F "file=@demo-data/heat-safety-policy.pdf"
```

Record the returned `jobId`.

```bash
curl "$BASE_URL/ingestion/jobs?chatId=$CHAT_ID&limit=5" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

If the queue worker is disabled in a local profile, process one job manually:

```bash
curl -X POST "$BASE_URL/ingestion/jobs/process?jobId=<jobId>" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

## 4. Run the Walkthrough Questions

| Scenario | Question or action | Expected signal |
|---|---|---|
| PDF upload | Upload `demo-data/heat-safety-policy.pdf` | Ingestion job is created with queue backend and job status. |
| Async ingestion | Query `/ingestion/jobs?chatId=heat-safety-demo` | Job reaches `SUCCEEDED` or exposes retry/error details. |
| Retrieval hit | `Summarize heat exposure control requirements.` | Answer refers to hydration breaks, rotation, recovery areas, and supervisor review. |
| Citation source | `Which source supports the no-fabrication rule?` | Answer includes citations such as `source=heat-safety-policy.pdf`. |
| Evidence snippets | Ask through the console RAG workflow | Citation chips and evidence snippets are visible in the answer. |
| Empty fallback | `What is the travel reimbursement policy?` | Assistant says the current knowledge base has no matching content. |
| Tenant isolation | Repeat the same RAG question with another `X-Tenant-Id` | No cross-tenant policy content is returned. |
| Permission failure | Call a protected admin route without valid auth | Request is rejected and can be inspected through audit logs. |

## 5. Verify Runtime Evidence

```bash
./scripts/demo.sh verify
python3 scripts/run_regression.py \
  --dataset evaluation/dataset.large.json \
  --predictions evaluation/predictions.sample.json \
  --threshold 0.70 \
  --correctness-threshold 0.75 \
  --citation-hit-threshold 0.70
```

Useful surfaces after the walkthrough:

- API health: `http://localhost:8080/actuator/health`
- Prometheus metrics: `http://localhost:8080/actuator/prometheus`
- Swagger UI: `http://localhost:8080/swagger-ui/index.html`
- Runtime logs: `./scripts/demo.sh logs`

## 6. Clean Up

```bash
./scripts/demo.sh down
```
