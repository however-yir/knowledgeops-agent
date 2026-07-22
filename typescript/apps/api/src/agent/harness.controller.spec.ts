import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { env } from "../config/env.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { HarnessController } from "./harness.controller.js";
import { McpClient } from "./mcp.client.js";

function controller(store = new PlatformStore()) {
  return new HarnessController(store, new RetrievalService(store), new BusinessToolsService(store, new MetricsService(store)), new McpClient());
}

describe("HarnessController", () => {
  it("keeps trusted runtime disabled by default", () => {
    const result = controller().preview("public", {
      action: "workspace_read_file",
      actionInput: { path: "README.md" }
    });

    expect(result.ok).toBe(0);
    expect(result.preview.status).toBe("blocked");
    expect(result.preview.decision.message).toBe("trusted runtime is disabled");
    expect("token" in result).toBe(false);
  });

  it("rejects default runtime actions from trusted preview", () => {
    const previous = env.APP_AGENT_HARNESS_TRUSTED_ENABLED;
    env.APP_AGENT_HARNESS_TRUSTED_ENABLED = true;
    try {
      const result = controller().preview("public", {
        action: "query_course",
        actionInput: { type: "编程", edu: 2 }
      });

      expect(result.ok).toBe(0);
      expect(result.preview.decision.message).toContain("does not require trusted runtime");
      expect("token" in result).toBe(false);
    } finally {
      env.APP_AGENT_HARNESS_TRUSTED_ENABLED = previous;
    }
  });

  it("binds one-time trusted tokens to the authenticated tenant", async () => {
    const previous = env.APP_AGENT_HARNESS_TRUSTED_ENABLED;
    env.APP_AGENT_HARNESS_TRUSTED_ENABLED = true;
    try {
      const instance = controller();
      const preview = instance.preview("tenant-a", {
        action: "workspace_list_files",
        actionInput: { path: ".", maxDepth: 0 }
      });
      if (!("token" in preview) || typeof preview.token !== "string") {
        throw new Error("expected trusted action token");
      }

      expect(await instance.execute("tenant-b", preview.token)).toMatchObject({ status: "not_found" });
      expect(await instance.execute("tenant-a", preview.token)).toMatchObject({ status: "executed" });
      expect(await instance.execute("tenant-a", preview.token)).toMatchObject({ status: "not_found" });
    } finally {
      env.APP_AGENT_HARNESS_TRUSTED_ENABLED = previous;
    }
  });

  it("blocks workspace path traversal during trusted action preview", () => {
    const previous = env.APP_AGENT_HARNESS_TRUSTED_ENABLED;
    env.APP_AGENT_HARNESS_TRUSTED_ENABLED = true;
    try {
      const result = controller().preview("public", {
        action: "workspace_read_file",
        actionInput: { path: "../secret.txt" }
      });

      expect(result.ok).toBe(0);
      expect(result.preview.status).toBe("blocked");
      expect(result.preview.decision.message).toContain("escapes workspace root");
    } finally {
      env.APP_AGENT_HARNESS_TRUSTED_ENABLED = previous;
    }
  });
});
