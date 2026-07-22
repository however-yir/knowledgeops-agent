import { describe, expect, it } from "vitest";

import { env } from "../config/env.js";
import { PlatformStore, sessionKey } from "./platform.store.js";
import { PrismaPersistenceService } from "./prisma.persistence.service.js";

describe("PrismaPersistenceService", () => {
  it("hydrates tenant-scoped sessions from the authoritative database", async () => {
    const store = new PlatformStore();
    const service = new PrismaPersistenceService(store);
    const now = new Date("2026-07-22T00:00:00.000Z");
    const client = fakeClient({
      agentSessionState: [{
        sessionId: "same-id",
        tenantId: "tenant-a",
        title: "Persisted",
        workspaceId: "default",
        modelProfile: "balanced",
        streaming: true,
        pinned: false,
        archived: false,
        activeBranchId: "main",
        sessionPayload: JSON.stringify({ branches: [] }),
        createdAt: now,
        updatedAt: now
      }]
    });
    (service as unknown as { client: unknown }).client = client;

    await service.hydrate();

    expect(store.sessions.get(sessionKey("tenant-a", "same-id"))).toMatchObject({
      tenantId: "tenant-a",
      title: "Persisted"
    });
    expect(store.sessions.get(sessionKey("public", "same-id"))).toBeUndefined();
    expect(store.apiKeys.size).toBe(0);
  });

  it("surfaces persistence sink failures instead of swallowing them", async () => {
    const previousNodeEnv = env.NODE_ENV;
    const previousPrisma = env.APP_PRISMA_ENABLED;
    env.NODE_ENV = "development";
    env.APP_PRISMA_ENABLED = true;
    try {
      const store = new PlatformStore();
      store.registerPersistenceSink(async () => {
        throw new Error("database unavailable");
      });

      store.persist();

      await expect(store.waitForPersistence()).rejects.toThrow("database unavailable");
      expect(store.persistenceHealthy()).toBe(false);
    } finally {
      env.NODE_ENV = previousNodeEnv;
      env.APP_PRISMA_ENABLED = previousPrisma;
    }
  });
});

function fakeClient(overrides: Record<string, unknown[]> = {}) {
  const emptyModel = { findMany: async () => [] };
  return new Proxy({
    $connect: async () => undefined,
    $disconnect: async () => undefined,
    $transaction: async (value: unknown) => typeof value === "function" ? value(proxy) : Promise.all(value as Promise<unknown>[])
  } as Record<string, unknown>, {
    get(target, property: string) {
      if (property in target) {
        return target[property];
      }
      return {
        ...emptyModel,
        findMany: async () => overrides[property] ?? []
      };
    }
  });
  function proxy() {
    return undefined;
  }
}
