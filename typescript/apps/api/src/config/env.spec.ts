import { describe, expect, it } from "vitest";

import { env, type AppEnv, validateRuntimeConfig } from "./env.js";

describe("validateRuntimeConfig", () => {
  it("rejects disabled security and placeholder JWT secrets in production", () => {
    expect(() => validateRuntimeConfig(config({ APP_SECURITY_ENABLED: false }))).toThrow("APP_SECURITY_ENABLED");
    expect(() => validateRuntimeConfig(config({ APP_JWT_SECRET: "replace_with_32_bytes_min_secret" }))).toThrow("APP_JWT_SECRET");
  });

  it("rejects publicly committed seed credentials in production", () => {
    expect(() => validateRuntimeConfig(config({ APP_DEMO_API_KEY: "local-demo-api-key" }))).toThrow("APP_DEMO_API_KEY");
    expect(() => validateRuntimeConfig(config({ APP_DEMO_API_KEY: "dev-admin-key-2026" }))).toThrow("APP_DEMO_API_KEY");
    expect(() => validateRuntimeConfig(config({ APP_JWT_SECRET: "0123456789abcdef0123456789abcdef" }))).toThrow("APP_JWT_SECRET");
  });

  it("requires trusted runtime before workspace write or shell access", () => {
    expect(() => validateRuntimeConfig(config({ APP_WORKSPACE_WRITE_ENABLED: true }))).toThrow("APP_WORKSPACE_WRITE_ENABLED");
    expect(() => validateRuntimeConfig(config({ APP_WORKSPACE_SHELL_ENABLED: true }))).toThrow("APP_WORKSPACE_SHELL_ENABLED");
  });

  it("accepts hardened production settings", () => {
    expect(() => validateRuntimeConfig(config())).not.toThrow();
  });
});

function config(overrides: Partial<AppEnv> = {}): AppEnv {
  return {
    ...env,
    NODE_ENV: "production",
    APP_SECURITY_ENABLED: true,
    APP_JWT_SECRET: "ci-production-jwt-secret-0123456789abcdef",
    APP_DEMO_API_KEY: "ci-explicit-production-key",
    APP_PRISMA_ENABLED: true,
    DATABASE_URL: "mysql://app:secret@mysql:3306/knowledgeops_agent",
    APP_AGENT_HARNESS_TRUSTED_ENABLED: false,
    APP_WORKSPACE_WRITE_ENABLED: false,
    APP_WORKSPACE_SHELL_ENABLED: false,
    ...overrides
  };
}
