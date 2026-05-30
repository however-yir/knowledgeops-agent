import { describe, expect, it } from "vitest";

import { HealthController } from "./health.controller.js";

describe("HealthController", () => {
  it("returns a Java-compatible health status", () => {
    const controller = new HealthController();

    expect(controller.health()).toEqual({ status: "UP" });
  });
});
