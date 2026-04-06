# Performance SLO

- p95 latency: `< 1500ms`
- throughput: `>= 80 req/s` (chat + rag mixed)
- error rate: `< 2%`
- ingestion retry success rate: `>= 99%` within max retries
- dlq ratio: `< 0.5%`

## Run k6

```bash
k6 run performance/k6/chat_ingestion_load.js -e BASE_URL=http://localhost:8080
python3 performance/k6/generate_report.py --summary reports/performance/distributed-k6-summary.json
```
