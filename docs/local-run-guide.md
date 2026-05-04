# 本地运行指南

## 环境要求

- JDK 17+
- Maven 3.9+
- Docker & Docker Compose
- 8GB+ 可用内存

## 5 分钟快速启动

```bash
git clone https://github.com/however-yir/knowledgeops-agent.git
cd knowledgeops-agent
./scripts/demo.sh
```

启动后访问：
- 前端控制台：http://localhost:8088
- 后端 API：http://localhost:8080
- Swagger UI：http://localhost:8080/swagger-ui/index.html

## 手动启动（分步骤）

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 OPENAI_API_KEY（必填）
```

核心环境变量：
| 变量 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_API_KEY` | 模型 API 密钥 | 必填 |
| `OPENAI_BASE_URL` | 模型网关地址 | `https://api.openai.com` |
| `DB_URL` | MySQL 连接 | `jdbc:mysql://localhost:3306/knowledgeops_agent` |
| `APP_VECTOR_STORE_BACKEND` | 向量存储后端 | `pgvector` 或 `simple` |
| `APP_JWT_SECRET` | JWT 签名密钥 | 生产必填 |

### 2. 启动中间件

```bash
docker compose up -d mysql redis rabbitmq
```

### 3. 启动应用

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=dev
```

### 4. 启动前端（可选）

```bash
cd frontend
npm install
npm run dev
```

## Docker Compose 完整启动

```bash
docker compose up --build -d
```

服务列表：
| 服务 | 端口 | 说明 |
|---|---|---|
| knowledgeops-agent | 8080 | Spring Boot 后端 |
| knowledgeops-agent-mysql | 3306 | MySQL 8.x |
| knowledgeops-agent-redis | 6379 | Redis 7.x |
| knowledgeops-agent-rabbitmq | 5672/15672 | RabbitMQ |
| knowledgeops-agent-web | 8088 | Vue 3 前端 (Nginx) |

## 可观测栈（可选）

```bash
docker compose -f docker-compose.observability.yml up -d
```

包含 Prometheus、Grafana、Loki、Tempo、Alertmanager。

Grafana：http://localhost:3000（默认 admin/admin）

## 无模型密钥模式

使用 Ollama 本地模型：

```bash
# 1. 安装 Ollama
brew install ollama  # macOS

# 2. 拉取模型
ollama pull qwen3:1.7b

# 3. 配置 application-dev.yml
# spring.ai.ollama.base-url=http://localhost:11434
# spring.ai.ollama.chat.model=qwen3:1.7b
```

向量存储切到 `simple` 模式（无需 pgvector）：

```yaml
app:
  vector-store:
    backend: simple
```

## 验证启动

```bash
# 健康检查
curl http://localhost:8080/actuator/health

# 简单问答
curl -X POST http://localhost:8080/ai/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: public" \
  -d '{"prompt": "你好", "chatId": "test-1"}'
```

## 常见问题

| 问题 | 解决 |
|---|---|
| `Connection refused` | 检查 Docker 是否运行，端口是否被占用 |
| `401 Unauthorized` | 检查 API Key 是否正确，或使用 demo API Key |
| `Flyway migration failed` | 检查 MySQL 是否可连接，数据库是否存在 |
| 向量检索为空 | 检查 pgvector 是否运行，向量数据是否已入库 |
| 前端白屏 | 检查 nginx 配置，或直接 `cd frontend && npm run dev` |

## tianji-ai-agent 联调

KnowledgeOps 作为 tianji 的能力底座时，配置 tianji 的 `application.yml`：

```yaml
tj:
  ai:
    knowledgeops:
      base-url: http://localhost:8080
      enabled: true
```
