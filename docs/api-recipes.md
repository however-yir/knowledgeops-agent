# API Recipes

These recipes assume the local Docker Compose stack is running on `http://localhost:8080`.

## Common Headers

```bash
export BASE_URL=http://localhost:8080
export API_KEY=<local-demo-api-key>
export TENANT_ID=default
```

Most local examples can use the seeded API key:

```bash
-H "X-API-Key: $API_KEY" -H "X-Tenant-Id: $TENANT_ID"
```

For JWT-based calls, set `API_KEY` to the seeded development value from `.env.example`, then exchange the API key first:

```bash
curl -X POST "$BASE_URL/auth/token" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

## Chat

```bash
curl "$BASE_URL/ai/chat?prompt=Summarize%20KnowledgeOps%20Agent&chatId=demo-chat" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

Optional query parameters:

- `modelProfile=economy`
- `modelProfile=balanced`
- `modelProfile=quality`

## Upload a PDF for Ingestion

```bash
curl -X POST "$BASE_URL/ingestion/upload/demo-rag" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID" \
  -H "X-Idempotency-Key: demo-rag-001" \
  -F "file=@/path/to/document.pdf"
```

Check the returned `jobId`:

```bash
curl "$BASE_URL/ingestion/jobs/<jobId>" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

List recent ingestion jobs for a chat:

```bash
curl "$BASE_URL/ingestion/jobs?chatId=demo-rag&limit=20" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

## Ask the PDF RAG Endpoint

```bash
curl "$BASE_URL/ai/pdf/chat?prompt=What%20are%20the%20key%20points%3F&chatId=demo-rag" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

The response includes answer text and citation lines when matching sources are available.

## ReAct Agent

JSON response:

```bash
curl -X POST "$BASE_URL/ai/react/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID" \
  -d '{"prompt":"Find the next useful operations check","chatId":"react-demo","modelProfile":"balanced"}'
```

SSE stream:

```bash
curl -N -X POST "$BASE_URL/ai/react/chat/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID" \
  -d '{"prompt":"Explain the ingestion pipeline","chatId":"react-stream-demo"}'
```

## History and Audit

```bash
curl "$BASE_URL/ai/history/chat" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"

curl "$BASE_URL/audit/logs" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID"
```

## Health and Observability

```bash
curl "$BASE_URL/actuator/health"
curl "$BASE_URL/actuator/prometheus"
```

For logs, traces, alerting, and drill workflows, continue with [Operations Manual](operations.md).
