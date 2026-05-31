import { describe, expect, it } from "vitest";

import { RetrievalService } from "../ai/retrieval.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { HarnessController } from "./harness.controller.js";

describe("HarnessController", () => {
  it("blocks workspace path traversal during trusted action preview", () => {
    const controller = new HarnessController(new PlatformStore(), new RetrievalService(new PlatformStore()));

    const preview = controller.preview({ action: "workspace_read_file", actionInput: { path: "../secret.txt" } });

    expect(preview.ok).toBe(0);
    expect(preview.preview.status).toBe("blocked");
  });
});
