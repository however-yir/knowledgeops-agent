import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  APP_SECURITY_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_JWT_SECRET: z.string().min(16).default("dev-only-change-me-secret"),
  APP_JWT_EXPIRE_MINUTES: z.coerce.number().int().min(1).default(120),
  APP_REFRESH_EXPIRE_DAYS: z.coerce.number().int().min(1).default(14),
  APP_DEMO_API_KEY: z.string().min(1).default("local-demo-api-key"),
  APP_CORS_ALLOWED_ORIGINS: z.string().default("http://localhost:8088,http://localhost:5173"),
  APP_INGESTION_STORAGE_DIR: z.string().default("./data/uploads"),
  APP_INGESTION_QUEUE_BACKEND: z.enum(["in-memory", "db_polling", "redis_stream", "rabbitmq"]).default("in-memory"),
  APP_REDIS_URL: z.string().default("redis://localhost:6379"),
  APP_REDIS_STREAM_KEY: z.string().default("knowledgeops:ingestion"),
  APP_REDIS_DLQ_STREAM_KEY: z.string().default("knowledgeops:ingestion:dlq"),
  APP_REDIS_CONSUMER_GROUP: z.string().default("knowledgeops-workers"),
  APP_REDIS_CONSUMER_NAME: z.string().default("worker-1"),
  APP_INGESTION_CLAIM_IDLE_MS: z.coerce.number().int().min(1000).default(30000),
  APP_RABBITMQ_URL: z.string().default("amqp://guest:guest@localhost:5672"),
  APP_RABBITMQ_EXCHANGE: z.string().default("ingestion.exchange"),
  APP_RABBITMQ_ROUTING_KEY: z.string().default("ingestion.jobs"),
  APP_RABBITMQ_QUEUE: z.string().default("ingestion.jobs.queue"),
  APP_RABBITMQ_DLQ_EXCHANGE: z.string().default("ingestion.dlx"),
  APP_RABBITMQ_DLQ_ROUTING_KEY: z.string().default("ingestion.jobs.dlq"),
  APP_RABBITMQ_DLQ_QUEUE: z.string().default("ingestion.jobs.dlq.queue"),
  APP_RABBITMQ_CONFIRM_TIMEOUT_MS: z.coerce.number().int().min(1000).default(5000),
  APP_INGESTION_WORKER_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_INGESTION_WORKER_INTERVAL_MS: z.coerce.number().int().min(250).default(2000),
  APP_INGESTION_WORKER_CONCURRENCY: z.coerce.number().int().min(1).default(2),
  APP_INGESTION_MAX_FILE_BYTES: z.coerce.number().int().min(1).default(20 * 1024 * 1024),
  APP_ALLOWED_UPLOAD_MIME_TYPES: z.string().default("text/plain,text/markdown,application/pdf,application/octet-stream"),
  APP_INGESTION_MAX_RETRIES: z.coerce.number().int().min(1).default(3),
  APP_INGESTION_BASE_DELAY_SECONDS: z.coerce.number().int().min(1).default(30),
  APP_STATE_FILE: z.string().default("./data/state.json"),
  APP_WORKSPACE_ROOT: z.string().default(process.cwd()),
  APP_PRISMA_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  DATABASE_URL: z.string().default(""),
  APP_LLM_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  OPENAI_API_KEY: z.string().default(""),
  OPENAI_BASE_URL: z.string().url().default("https://api.openai.com/v1"),
  APP_LLM_TIMEOUT_MS: z.coerce.number().int().min(1000).default(30000),
  APP_LLM_MAX_RETRIES: z.coerce.number().int().min(0).default(2),
  APP_LLM_TEMPERATURE: z.coerce.number().min(0).max(2).default(0.2),
  APP_LLM_SYSTEM_PROMPT: z.string().default("You are KnowledgeOps Agent. Answer from the provided evidence only. If evidence is insufficient, clearly say what is missing. Preserve numbered citations such as [1] and [2]."),
  APP_LLM_LOCAL_FALLBACK_ENABLED: z.preprocess(
    (value) => value === true || value === "true",
    z.boolean()
  ).default(process.env.NODE_ENV !== "production"),
  APP_LLM_FALLBACK_BASE_URL: z.string().default(""),
  APP_LLM_FALLBACK_API_KEY: z.string().default(""),
  APP_LLM_FALLBACK_MODEL: z.string().default(""),
  APP_MODEL_ECONOMY: z.string().default("gpt-4.1-mini"),
  APP_MODEL_BALANCED: z.string().default("gpt-4.1"),
  APP_MODEL_QUALITY: z.string().default("gpt-4.1"),
  APP_MODEL_DEFAULT_PROFILE: z.string().default("balanced"),
  APP_MODEL_AB_QUALITY_PERCENT: z.coerce.number().int().min(0).max(100).default(50),
  APP_VECTOR_BACKEND: z.enum(["local", "pgvector"]).default("local"),
  APP_VECTOR_LOCAL_FALLBACK_ENABLED: z.preprocess(
    (value) => value === true || value === "true",
    z.boolean()
  ).default(process.env.NODE_ENV !== "production"),
  APP_PGVECTOR_URL: z.string().default(""),
  APP_PGVECTOR_SCHEMA: z.string().regex(/^[a-zA-Z_][a-zA-Z0-9_]*$/).default("public"),
  APP_PGVECTOR_TABLE: z.string().regex(/^[a-zA-Z_][a-zA-Z0-9_]*$/).default("ai_knowledge_chunks"),
  APP_PGVECTOR_DIMENSIONS: z.coerce.number().int().min(1).default(1024),
  APP_PGVECTOR_INITIALIZE_SCHEMA: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_EMBEDDING_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_EMBEDDING_MODEL: z.string().default("text-embedding-3-small"),
  APP_EMBEDDING_BASE_URL: z.string().url().default("https://api.openai.com/v1"),
  APP_WEB_SEARCH_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WEB_SEARCH_BACKEND: z.enum(["generic", "searxng", "bing"]).default("generic"),
  APP_WEB_SEARCH_ENDPOINT: z.string().default(""),
  APP_WEB_SEARCH_SEARXNG_URL: z.string().default(""),
  APP_WEB_SEARCH_BING_API_KEY: z.string().default(""),
  APP_WEB_SEARCH_BING_ENDPOINT: z.string().default("https://api.bing.microsoft.com/v7.0"),
  APP_WEB_SEARCH_MAX_RESULTS: z.coerce.number().int().min(1).default(5),
  APP_WEB_SEARCH_TIMEOUT_MS: z.coerce.number().int().min(1000).default(8000),
  APP_RATE_LIMIT_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_RATE_LIMIT_CAPACITY: z.coerce.number().int().min(1).default(120),
  APP_RATE_LIMIT_REFILL_SECONDS: z.coerce.number().int().min(1).default(60),
  APP_RATE_LIMIT_EVICT_INTERVAL_MS: z.coerce.number().int().min(1).default(300000),
  APP_DISTRIBUTED_RATE_LIMIT_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_AUDIT_RETENTION_DAYS: z.coerce.number().int().min(1).default(90),
  APP_OBSERVABILITY_TRACE_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WORKFLOW_ASYNC_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WORKFLOW_WORKER_INTERVAL_MS: z.coerce.number().int().min(250).default(2000),
  APP_FEEDBACK_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_FEEDBACK_DATASET_PATH: z.string().min(1).default("evaluation/feedback_dataset.jsonl"),
  APP_MCP_HTTP_ALLOWLIST: z.string().default(""),
  APP_MCP_SERVERS_JSON: z.string().default("{}"),
  APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS: z.string().default(""),
  APP_AGENT_HARNESS_TRUSTED_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WORKSPACE_WRITE_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WORKSPACE_SHELL_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WORKSPACE_ALLOWED_COMMANDS: z.string().default("pwd,ls,rg,git"),
  APP_WORKSPACE_ALLOWED_GIT_SUBCOMMANDS: z.string().default("status,diff,show,log"),
  APP_WORKSPACE_COMMAND_TIMEOUT_SECONDS: z.coerce.number().int().min(1).max(30).default(10),
  APP_WORKSPACE_MAX_COMMAND_OUTPUT_BYTES: z.coerce.number().int().min(1).default(20000),
  APP_COST_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_COST_DEFAULT_MONTHLY_BUDGET_USD: z.coerce.number().min(0).default(25),
  APP_COST_DEFAULT_HARD_LIMIT_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_COST_TOKEN_ESTIMATE_DIVISOR: z.coerce.number().int().min(1).default(4),
  APP_COST_USD_PER_1K_LOW: z.coerce.number().min(0).default(0.001),
  APP_COST_USD_PER_1K_BALANCED: z.coerce.number().min(0).default(0.003),
  APP_COST_USD_PER_1K_HIGH: z.coerce.number().min(0).default(0.008),
  RAG_CHUNK_SIZE: z.coerce.number().int().min(200).default(800),
  RAG_MIN_CHUNK_SIZE: z.coerce.number().int().min(1).default(120),
  RAG_MAX_NUM_CHUNKS: z.coerce.number().int().min(1).default(100),
  RAG_SIMILARITY_THRESHOLD: z.coerce.number().min(0).max(1).default(0.45),
  RAG_RETRIEVE_TOP_K: z.coerce.number().int().min(1).default(12),
  RAG_RERANK_TOP_K: z.coerce.number().int().min(1).default(6),
  RAG_TEMPERATURE: z.coerce.number().min(0).max(2).default(0.2),
  RAG_ANSWER_SYSTEM_PROMPT: z.string().default("你是一个RAG问答助手。必须仅根据给定上下文作答，输出结尾附上引用编号，例如 [1][2]。如果上下文不足请明确说明。"),
  RAG_HYBRID_SYSTEM_PROMPT: z.string().default("你是一个企业级RAG问答助手。必须仅根据给定上下文作答，输出结尾附上引用编号，例如 [1][2]。如果上下文不足请明确说明。"),
  RAG_RERANK_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  RAG_RERANK_ENDPOINT: z.string().default(""),
  RAG_EVIDENCE_JUDGE_MIN_SCORE: z.coerce.number().min(0).max(1).default(0.08),
  RAG_EVIDENCE_JUDGE_ENDPOINT: z.string().default(""),
  APP_REACT_MAX_STEPS: z.coerce.number().int().min(1).max(10).default(4),
  APP_REACT_PLANNER_SYSTEM_PROMPT: z.string().default("You are a strict JSON ReAct planner. Return valid JSON only."),
  APP_REACT_FINAL_SYSTEM_PROMPT: z.string().default("你是企业级AI助手，请结合轨迹和观察信息给出最终答案。"),
  APP_AUDIT_RETENTION_WORKER_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_AUDIT_RETENTION_INTERVAL_MS: z.coerce.number().int().min(1000).default(60_000),
  APP_JAVA_BASE_URL: z.string().default(""),
  APP_TS_BASE_URL: z.string().default("")
});

export const env = envSchema.parse(process.env);

export type AppEnv = typeof env;

const FORBIDDEN_JWT_SECRETS = new Set([
  "dev-only-change-me-secret",
  "replace_with_32_bytes_min_secret",
  "replace-me-with-real-secret",
  "change-me",
  "changeme"
]);

export function validateRuntimeConfig(config: AppEnv = env): void {
  if (config.NODE_ENV !== "production") {
    return;
  }
  if (!config.APP_SECURITY_ENABLED) {
    throw new Error("APP_SECURITY_ENABLED must be true in production");
  }
  if (!config.APP_PRISMA_ENABLED || !config.DATABASE_URL.trim()) {
    throw new Error("APP_PRISMA_ENABLED and DATABASE_URL are required in production");
  }
  if (Buffer.byteLength(config.APP_JWT_SECRET, "utf8") < 32 || FORBIDDEN_JWT_SECRETS.has(config.APP_JWT_SECRET)) {
    throw new Error("APP_JWT_SECRET must be at least 32 bytes and must not use a placeholder in production");
  }
  if (config.APP_WORKSPACE_WRITE_ENABLED && !config.APP_AGENT_HARNESS_TRUSTED_ENABLED) {
    throw new Error("APP_WORKSPACE_WRITE_ENABLED requires APP_AGENT_HARNESS_TRUSTED_ENABLED");
  }
  if (config.APP_WORKSPACE_SHELL_ENABLED && !config.APP_AGENT_HARNESS_TRUSTED_ENABLED) {
    throw new Error("APP_WORKSPACE_SHELL_ENABLED requires APP_AGENT_HARNESS_TRUSTED_ENABLED");
  }
}
