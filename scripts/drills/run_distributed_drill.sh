#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
BEARER_TOKEN="${BEARER_TOKEN:-}"
OUT_DIR="reports/performance"
mkdir -p "${OUT_DIR}"

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is required. Install k6 first."
  exit 1
fi

echo "[1/3] Start observability stack"
docker compose -f docker-compose.observability.yml up -d

echo "[2/3] Run distributed load test"
k6 run performance/k6/distributed_chat_ingestion.js \
  -e BASE_URL="${BASE_URL}" \
  -e BEARER_TOKEN="${BEARER_TOKEN}" \
  --summary-export "${OUT_DIR}/distributed-k6-summary.json"

echo "[3/3] Drill finished"
echo "summary: ${OUT_DIR}/distributed-k6-summary.json"
