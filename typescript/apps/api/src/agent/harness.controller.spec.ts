import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { HarnessController } from "./harness.controller.js";

describe("HarnessController", () => {
  it("blocks workspace path traversal during trusted action preview", () => {
    const store = new PlatformStore();
    const controller = new HarnessController(store, new RetrievalService(store), new BusinessToolsService(store, new MetricsService(store)));

    const preview = controller.preview({ action: "workspace_read_file", actionInput: { path: "../secret.txt" } });

    expect(preview.ok).toBe(0);
    expect(preview.preview.status).toBe("blocked");
  });

  it("executes Java-parity builtin course tools", async () => {
    const store = new PlatformStore();
    const controller = new HarnessController(store, new RetrievalService(store), new BusinessToolsService(store, new MetricsService(store)));
    const preview = controller.preview({ action: "query_course", actionInput: { type: "编程", edu: 2 } });

    const result = await controller.execute(preview.token);

    expect(result.status).toBe("executed");
    expect(JSON.stringify("observation" in result ? result.observation : result)).toContain("Java编程实战");
  });
});
