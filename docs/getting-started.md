# Getting Started

This guide gets KnowledgeOps Agent running locally with Docker Compose and verifies the most important runtime surfaces.

## Prerequisites

- JDK 17+ if you plan to run the backend outside Docker.
- Docker and Docker Compose.
- An OpenAI-compatible model endpoint and API key.

## Start the Full Stack

```bash
git clone https://github.com/however-yir/knowledgeops-agent.git
cd knowledgeops-agent
./scripts/demo.sh
```

The demo script creates a gitignored `.env.demo` file when missing, starts the Docker Compose stack, waits for API/web health checks, and runs a smoke test.

```bash
make demo
```

Use `make demo` when you prefer Make targets.

## Verify Startup

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/prometheus
```

Expected local surfaces:

| Surface | URL |
|---|---|
| Frontend console | `http://localhost:8088` |
| Backend API | `http://localhost:8080` |
| Swagger UI | `http://localhost:8080/swagger-ui/index.html` |
| RabbitMQ console | `http://localhost:15672` |

## Authenticate

The local development seed includes a demo administrator API key. Use the seeded value from `.env.example` or the frontend authentication card.

```bash
curl -X POST http://localhost:8080/auth/token \
  -H "X-API-Key: <local-demo-api-key>" \
  -H "X-Tenant-Id: default"
```

Use the returned JWT as `Authorization: Bearer <token>` for protected routes. The API key can also be sent directly with `X-API-Key` in local evaluation flows.

## Try a Chat Request

```bash
curl "http://localhost:8080/ai/chat?prompt=hello&chatId=demo-chat" \
  -H "X-API-Key: <local-demo-api-key>" \
  -H "X-Tenant-Id: default"
```

## Shut Down

```bash
./scripts/demo.sh down
```

Use `docker compose down -v` only when you intentionally want to remove local volumes.

## Demo Script Commands

```bash
./scripts/demo.sh verify
./scripts/demo.sh logs
./scripts/demo.sh down
```

Use `DEMO_RESET=1 ./scripts/demo.sh` when you intentionally want to remove demo volumes before startup.

## Next Steps

- Run the full [Reproducible Demo Script](demo-script.md) with `demo-data/heat-safety-policy.pdf`.
- Use [API Recipes](api-recipes.md) for common endpoint examples.
- Read [Enterprise Architecture](architecture-enterprise.md) before changing data flow or security boundaries.
- Read [Operations Manual](operations.md) before running drills, load tests, or observability components.
