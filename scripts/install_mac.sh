#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

log() {
  printf '[knowledgeops-agent][install][mac] %s\n' "$1"
}

fail() {
  printf '[knowledgeops-agent][install][mac][error] %s\n' "$1" >&2
  exit 1
}

ensure_env_file() {
  if [[ -f ".env" ]]; then
    return
  fi

  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    log "Created .env from .env.example"
  else
    touch .env
    log "Created empty .env"
  fi
}

get_env_value() {
  local key="$1"
  awk -F= -v env_key="$key" '$1 == env_key {sub(/^[^=]*=/, "", $0); print $0; exit}' .env
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"

  if grep -q "^${key}=" .env; then
    sed -i '' "s/^${key}=.*/${key}=${escaped}/" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
}

require_command() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
}

log "Checking prerequisites..."
require_command docker
docker info >/dev/null 2>&1 || fail "Docker is not running. Start Docker Desktop first."

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  fail "Docker Compose is not available. Install Docker Compose plugin first."
fi

ensure_env_file

current_key="${OPENAI_API_KEY:-$(get_env_value OPENAI_API_KEY)}"
if [[ -z "${current_key}" || "${current_key}" == "replace_me" || "${current_key}" == "sk-local-dev-placeholder" ]]; then
  printf 'Please enter OPENAI_API_KEY (input hidden): '
  read -r -s input_key
  printf '\n'
  [[ -z "${input_key}" ]] && fail "OPENAI_API_KEY cannot be empty."
  set_env_value OPENAI_API_KEY "${input_key}"
  log "Saved OPENAI_API_KEY to .env"
fi

log "Starting containers..."
"${COMPOSE_CMD[@]}" up --build -d

cat <<'EOF'
[knowledgeops-agent][install][mac] Done.
- Frontend Console: http://localhost:8088
- Backend API:      http://localhost:8080
- RabbitMQ Console: http://localhost:15672

Demo API Key (local only): dev-admin-key-2026
EOF
