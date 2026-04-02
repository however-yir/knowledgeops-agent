# Operations Guide

## Observability Stack

```bash
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Tempo: `http://localhost:3200`
- Alertmanager: `http://localhost:9093`

## Alert Rules

- HighHttpP95Latency: p95 > 1.5s for 5m
- IngestionFailureRateHigh: ingestion failed rate > 5%

## Queue Backend

- Redis Stream: `APP_INGESTION_QUEUE_BACKEND=redis_stream`
- RabbitMQ: `APP_INGESTION_QUEUE_BACKEND=rabbitmq`
- DLQ stream/queue will receive terminal failed jobs.

## Log Shipping

- Application logs are emitted in JSON to `logs/ai-demo.log`.
- Promtail is configured to scrape `logs/*.log` and push to Loki.

## Regression (nightly)

```bash
python3 scripts/generate_eval_dataset.py
python3 scripts/generate_eval_predictions.py
python3 scripts/run_regression.py --dataset evaluation/dataset.large.json --predictions evaluation/predictions.generated.json --threshold 0.75
```

## Performance

```bash
k6 run performance/k6/chat_ingestion_load.js -e BASE_URL=http://localhost:8080
```
