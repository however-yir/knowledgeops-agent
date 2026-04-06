# Enterprise Deployment Guide

## 1. Target Topology

Recommended baseline for production:

- API service: 2-3 stateless instances
- MySQL: managed HA or primary-replica
- Redis: sentinel/cluster mode
- RabbitMQ: mirrored queues or managed MQ
- Vector storage: PostgreSQL + pgvector (dedicated)
- Observability: Prometheus + Loki + Tempo + Alertmanager

## 2. Required Environment Variables

Mandatory:

- `OPENAI_API_KEY`
- `APP_JWT_SECRET` (32+ bytes)
- `DB_URL`
- `DB_USERNAME`
- `DB_PASSWORD`

Strongly recommended:

- `APP_SECURITY_ENABLED=true`
- `APP_RATE_LIMIT_ENABLED=true`
- `APP_MODEL_ROUTER_ENABLED=true`
- `APP_MODEL_ROUTER_DEFAULT_PROFILE=balanced`
- `APP_VECTOR_STORE_BACKEND=pgvector`
- `APP_REQUIRE_PGVECTOR=true`

## 3. Release Sequence

1. Build image:
   - `docker build -t iqk-platform:<tag> .`
2. Apply DB migration (Flyway at startup or pipeline stage).
3. Deploy canary instance.
4. Verify:
   - `/actuator/health`
   - `/actuator/prometheus`
   - key APIs (`/ai/chat`, `/ai/pdf/chat`, `/auth/token`)
5. Shift traffic gradually.
6. Run post-deploy smoke + regression.

## 4. Rollback Strategy

- Keep previous image tag warm.
- Roll back service image first.
- For schema changes, ensure backward-compatible migration before release.
- If queue backlog spikes, pause ingestion consumers and drain gradually.

## 5. SLO Suggestions

- Chat API availability: >= 99.9%
- `/ai/chat` p95 latency: <= 1500 ms
- Ingestion failure ratio (5m): <= 5%
- MTTR for critical alerts: <= 30 min

## 6. Pre-Production Checklist

- [ ] Secrets loaded from Vault/KMS/Secret Manager
- [ ] API Key issue/revoke flow verified
- [ ] JWT refresh flow verified
- [ ] Ingestion retry + DLQ verified
- [ ] Dashboard and alert routes verified
- [ ] Load test baseline recorded
- [ ] Backup and restore tested (MySQL + vector storage)
