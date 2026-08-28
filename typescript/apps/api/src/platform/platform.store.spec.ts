import { createHash } from "node:crypto";

import { afterEach, describe, expect, it } from "vitest";

import { env } from "../config/env.js";
import { PlatformStore } from "./platform.store.js";

function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

describe("PlatformStore demo key seeding", () => {
  const originalNodeEnv = env.NODE_ENV;
  const originalBootstrap = env.APP_BOOTSTRAP_DEMO_KEY;

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv;
    env.APP_BOOTSTRAP_DEMO_KEY = originalBootstrap;
  });

  it("seeds the demo admin key outside production", () => {
    env.NODE_ENV = "test";
    const store = new PlatformStore();

    expect(store.apiKeys.has(sha256Hex(env.APP_DEMO_API_KEY))).toBe(true);
  });

  it("does not seed the committed demo credential in production without an explicit bootstrap flag", () => {
    env.NODE_ENV = "production";
    env.APP_BOOTSTRAP_DEMO_KEY = false;
    const store = new PlatformStore();

    expect(store.apiKeys.has(sha256Hex(env.APP_DEMO_API_KEY))).toBe(false);
  });

  it("seeds the demo admin key in production when APP_BOOTSTRAP_DEMO_KEY is set", () => {
    env.NODE_ENV = "production";
    env.APP_BOOTSTRAP_DEMO_KEY = true;
    const store = new PlatformStore();

    expect(store.apiKeys.has(sha256Hex(env.APP_DEMO_API_KEY))).toBe(true);
  });
});
