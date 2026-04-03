# Distributed Load & Observability Drill

## Goal

Validate two production-critical links:

1. Distributed load stability (`multi app instances + queue backend + cache`)
2. Alerting loop closure (`Prometheus + Alertmanager + Loki + Tempo`)

## Topology (simulation)

- App: 2~3 instances (`docker compose --scale app=3`)
- Queue: Redis Streams or RabbitMQ
- Storage: MySQL + pgvector (optional)
- Observability: Prometheus + Alertmanager + Loki + Tempo + Promtail

## Runbook

1. Start stack:
`docker compose up -d`

2. Start observability stack:
`docker compose -f docker-compose.observability.yml up -d`

3. Run distributed load:
`k6 run performance/k6/distributed_chat_ingestion.js -e BASE_URL=http://localhost:8080 -e BEARER_TOKEN=xxx`

4. Inject failure drill (optional):
- stop one app instance
- stop queue consumer process once

5. Verify metrics:
- p95 latency
- error rate
- queue lag
- retry success rate

6. Verify traces/logs:
- trace has `request_id/trace_id/session_id/job_id`
- logs can be filtered by `trace_id`

7. Verify alert closure:
- trigger: high latency / error spike
- alertmanager receives alert
- recovery alert appears after load stop

## Deliverables

- `reports/performance/distributed-k6-summary.json`
- screenshot of Grafana dashboards
- screenshot of firing + resolved alerts
- one-page postmortem note
