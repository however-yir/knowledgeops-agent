import { describe, expect, it } from "vitest";

import { env } from "../config/env.js";
import { PlatformStore, sessionKey, type TenantUsageDailyRecord } from "./platform.store.js";
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

  it("persists only usage deltas and advances the baseline after commit", async () => {
    const previousPrisma = env.APP_PRISMA_ENABLED;
    const previousUrl = env.DATABASE_URL;
    env.APP_PRISMA_ENABLED = true;
    env.DATABASE_URL = "mysql://test";
    try {
      const store = new PlatformStore();
      store.tenantUsageDaily.set("public:2026-07-22", usage(2, 20, 10, 0.004));
      const service = new PrismaPersistenceService(store);
      const { client, usageUpserts, failNextTransaction } = recordingClient();
      (service as unknown as { client: unknown }).client = client;

      failNextTransaction();
      await expect(service.flush()).rejects.toThrow("transaction failed");
      await service.flush();

      expect(usageUpserts.at(-1)?.update).toMatchObject({
        requestCount: { increment: 2n },
        inputTokens: { increment: 20n },
        outputTokens: { increment: 10n },
        totalCostUsd: { increment: 0.004 }
      });

      store.tenantUsageDaily.set("public:2026-07-22", usage(3, 27, 15, 0.0055));
      await service.flush();

      expect(usageUpserts.at(-1)?.update).toMatchObject({
        requestCount: { increment: 1n },
        inputTokens: { increment: 7n },
        outputTokens: { increment: 5n },
        totalCostUsd: { increment: 0.0015 }
      });
    } finally {
      env.APP_PRISMA_ENABLED = previousPrisma;
      env.DATABASE_URL = previousUrl;
    }
  });
});

function usage(requestCount: number, inputTokens: number, outputTokens: number, totalCostUsd: number): TenantUsageDailyRecord {
  return {
    tenantId: "public",
    usageDate: "2026-07-22",
    requestCount,
    inputTokens,
    outputTokens,
    totalCostUsd,
    createdAt: "2026-07-22T00:00:00.000Z",
    updatedAt: "2026-07-22T00:00:00.000Z"
  };
}

function recordingClient() {
  const usageUpserts: Array<Record<string, any>> = [];
  let shouldFail = false;
  const noopModel = new Proxy({}, {
    get: () => async () => undefined
  });
  const client = new Proxy({
    tenantUsageDaily: {
      upsert: async (input: Record<string, any>) => {
        usageUpserts.push(input);
      }
    },
    $transaction: async (actions: Promise<unknown>[]) => {
      if (shouldFail) {
        shouldFail = false;
        await Promise.allSettled(actions);
        throw new Error("transaction failed");
      }
      return Promise.all(actions);
    }
  } as Record<string, unknown>, {
    get(target, property: string) {
      return property in target ? target[property] : noopModel;
    }
  });
  return {
    client,
    usageUpserts,
    failNextTransaction: () => {
      shouldFail = true;
    }
  };
}

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
