# Enterprise Architecture Notes

## 1. Bounded Contexts

- Conversation Context: chat, memory, history query
- Knowledge Context: upload, parse, chunk, embed, retrieve
- Security Context: api key lifecycle, jwt, permission checks
- Operations Context: metrics, logs, tracing, alerting, drills

## 2. Data Ownership

- MySQL:
  - `conversation` (chat history)
  - `ingestion_job` (async job state)
  - `users/roles/permissions/api_keys/audit_log`
  - business tables (`course/school/course_reservation`)
- Vector Store:
  - knowledge chunks and metadata
- Local or object storage:
  - original uploaded files

## 3. Reliability Design

- Idempotent ingestion by `X-Idempotency-Key`
- Retry with bounded attempts and delay backoff
- DLQ sink for terminal failures
- Queue backend abstraction (Redis Stream / RabbitMQ)

## 4. Security Design

- API Key for machine access bootstrap
- JWT for request-level authn/authz
- Refresh token rotation
- Tenant-scoped API key lifecycle (`X-Tenant-Id`)
- Tenant + principal composite rate limiting
- RBAC + route-level permission checks
- Audit log retention scheduler

## 5. Scalability Design

- Stateless API instances can be horizontally scaled
- Async ingestion decouples upload and vectorization cost
- Vector backend can switch from local/simple to pgvector
- Model router supports profile-based cost/quality routing
- Observability stack enables saturation and error trend diagnosis

## 6. Operational Recommendations

- Keep `chatId` stable in clients to preserve conversation continuity
- Set separate rate limits for chat and ingestion endpoints
- Run periodic regression tests before and after dependency upgrades
- Keep alert thresholds versioned together with code
