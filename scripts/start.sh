#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[iqk-platform] building..."
mvn -B -ntp -DskipTests clean package

echo "[iqk-platform] starting..."
java -jar target/iqk-platform-1.0-SNAPSHOT.jar
