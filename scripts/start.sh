#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[ai-demo] building..."
mvn -B -ntp -DskipTests clean package

echo "[ai-demo] starting..."
java -jar target/ai-demo-1.0-SNAPSHOT.jar
