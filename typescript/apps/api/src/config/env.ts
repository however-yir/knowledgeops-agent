import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  APP_SECURITY_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_JWT_SECRET: z.string().min(16).default("dev-only-change-me-secret"),
  APP_JWT_EXPIRE_MINUTES: z.coerce.number().int().min(1).default(120),
  APP_REFRESH_EXPIRE_DAYS: z.coerce.number().int().min(1).default(14),
  APP_DEMO_API_KEY: z.string().min(1).default("local-demo-api-key"),
  APP_CORS_ALLOWED_ORIGINS: z.string().default("http://localhost:8088,http://localhost:5173"),
  APP_INGESTION_STORAGE_DIR: z.string().default("./data/uploads"),
  APP_INGESTION_QUEUE_BACKEND: z.string().default("in-memory"),
  APP_INGESTION_MAX_RETRIES: z.coerce.number().int().min(1).default(3),
  APP_INGESTION_BASE_DELAY_SECONDS: z.coerce.number().int().min(1).default(30),
  APP_STATE_FILE: z.string().default("./data/state.json"),
  APP_WORKSPACE_ROOT: z.string().default(process.cwd()),
  APP_LLM_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  OPENAI_API_KEY: z.string().default(""),
  OPENAI_BASE_URL: z.string().url().default("https://api.openai.com/v1"),
  APP_MODEL_ECONOMY: z.string().default("gpt-4.1-mini"),
  APP_MODEL_BALANCED: z.string().default("gpt-4.1"),
  APP_MODEL_QUALITY: z.string().default("gpt-4.1"),
  APP_MODEL_DEFAULT_PROFILE: z.string().default("balanced"),
  APP_MODEL_AB_QUALITY_PERCENT: z.coerce.number().int().min(0).max(100).default(50),
  APP_WEB_SEARCH_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_WEB_SEARCH_ENDPOINT: z.string().default(""),
  APP_RATE_LIMIT_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_RATE_LIMIT_CAPACITY: z.coerce.number().int().min(1).default(120),
  APP_RATE_LIMIT_REFILL_SECONDS: z.coerce.number().int().min(1).default(60),
  APP_AUDIT_RETENTION_DAYS: z.coerce.number().int().min(1).default(90),
  APP_COST_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(true),
  APP_COST_DEFAULT_MONTHLY_BUDGET_USD: z.coerce.number().min(0).default(25),
  APP_COST_DEFAULT_HARD_LIMIT_ENABLED: z.preprocess((value) => value === true || value === "true", z.boolean()).default(false),
  APP_COST_TOKEN_ESTIMATE_DIVISOR: z.coerce.number().int().min(1).default(4),
  APP_COST_USD_PER_1K_LOW: z.coerce.number().min(0).default(0.001),
  APP_COST_USD_PER_1K_BALANCED: z.coerce.number().min(0).default(0.003),
  APP_COST_USD_PER_1K_HIGH: z.coerce.number().min(0).default(0.008),
  RAG_CHUNK_SIZE: z.coerce.number().int().min(200).default(800),
  RAG_MIN_CHUNK_SIZE: z.coerce.number().int().min(1).default(80),
  RAG_MAX_NUM_CHUNKS: z.coerce.number().int().min(1).default(200),
  RAG_SIMILARITY_THRESHOLD: z.coerce.number().min(0).max(1).default(0.05),
  RAG_RETRIEVE_TOP_K: z.coerce.number().int().min(1).default(8)
});

export const env = envSchema.parse(process.env);

export type AppEnv = typeof env;
