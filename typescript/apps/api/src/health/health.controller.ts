import { Controller, Get, Optional, ServiceUnavailableException } from "@nestjs/common";
import { ApiHealth, ok } from "@knowledgeops/shared";

import { env } from "../config/env.js";
import { PrismaPersistenceService } from "../platform/prisma.persistence.service.js";

@Controller()
export class HealthController {
  constructor(@Optional() private readonly persistence?: PrismaPersistenceService) {}

  @Get("actuator/health")
  actuatorHealth(): ApiHealth & { groups: string[] } {
    return { status: "UP", groups: ["liveness", "readiness"] };
  }

  @Get(["health", "actuator/health/liveness"])
  health(): ApiHealth {
    return { status: "UP" };
  }

  @Get("actuator/health/readiness")
  async readiness() {
    if (!this.persistence) {
      if (env.NODE_ENV === "production") {
        throw new ServiceUnavailableException({ status: "DOWN", components: { database: "DOWN", persistence: "DOWN" } });
      }
      return { status: "UP", components: { database: "DISABLED", persistence: "UP" } };
    }
    const components = await this.persistence.readiness();
    if (components.database !== "UP" || components.persistence !== "UP") {
      throw new ServiceUnavailableException({ status: "DOWN", components });
    }
    return { status: "UP", components };
  }

  @Get()
  root() {
    return ok({
      service: "knowledgeops-agent-typescript",
      status: "UP"
    });
  }
}
