# Operations Guide

## 1. Observability Stack Startup

```bash
docker compose -f docker-compose.observability.yml up -d
```

Access endpoints:

- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Tempo: `http://localhost:3200`
- Alertmanager: `http://localhost:9093`

## 2. Core Alerts

- `HighHttpP95Latency`: p95 > 1.5s for 5m
- `IngestionFailureRateHigh`: ingestion failed ratio > 5%

## 3. Queue Backend Modes

- Redis Stream: `APP_INGESTION_QUEUE_BACKEND=redis_stream`
- RabbitMQ: `APP_INGESTION_QUEUE_BACKEND=rabbitmq`
- DB polling fallback: `APP_INGESTION_QUEUE_BACKEND=db_polling`

Terminal failures enter DLQ stream/queue.

## 4. Log Shipping

- Application log file: `logs/knowledgeops-agent.log`
- Promtail scrapes `logs/*.log` and pushes to Loki
- Trace and request correlation fields: `trace_id`, `request_id`, `chat_id`

## 5. Nightly Regression

```bash
python3 scripts/generate_eval_dataset.py
python3 scripts/generate_eval_predictions.py
python3 scripts/run_regression.py --dataset evaluation/dataset.large.json --predictions evaluation/predictions.generated.json --threshold 0.75
```

## 6. Performance Validation

```bash
k6 run performance/k6/chat_ingestion_load.js -e BASE_URL=http://localhost:8080
k6 run performance/k6/distributed_chat_ingestion.js -e BASE_URL=http://localhost:8080
python3 performance/k6/generate_report.py --summary reports/performance/distributed-k6-summary.json
```

## 7. Incident Triage Playbook

1. Verify app health endpoint and dependency availability.
2. Check ingestion queue lag and failed jobs.
3. Correlate logs by `trace_id`.
4. Review p95 latency and error spikes in Prometheus.
5. Trigger fallback or rollback if SLA continues to degrade.
