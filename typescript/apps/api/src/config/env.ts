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
  APP_STATE_FILE: z.string().default("./data/state.json"),
  RAG_CHUNK_SIZE: z.coerce.number().int().min(200).default(800),
  RAG_RETRIEVE_TOP_K: z.coerce.number().int().min(1).default(8)
});

export const env = envSchema.parse(process.env);

export type AppEnv = typeof env;
