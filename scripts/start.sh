#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[knowledgeops-agent] building..."
mvn -B -ntp -DskipTests clean package

echo "[knowledgeops-agent] starting..."
java -jar target/knowledgeops-agent-1.0-SNAPSHOT.jar
