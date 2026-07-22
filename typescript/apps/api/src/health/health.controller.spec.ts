import { describe, expect, it } from "vitest";

import { HealthController } from "./health.controller.js";

describe("HealthController", () => {
  it("returns a Java-compatible actuator health status", () => {
    const controller = new HealthController();

    expect(controller.actuatorHealth()).toEqual({ status: "UP", groups: ["liveness", "readiness"] });
    expect(controller.health()).toEqual({ status: "UP" });
  });
});
