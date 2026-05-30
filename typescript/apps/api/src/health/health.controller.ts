import { Controller, Get } from "@nestjs/common";
import { ApiHealth, ok } from "@knowledgeops/shared";

@Controller()
export class HealthController {
  @Get("actuator/health")
  health(): ApiHealth {
    return {
      status: "UP"
    };
  }

  @Get()
  root() {
    return ok({
      service: "knowledgeops-agent-typescript",
      status: "UP"
    });
  }
}
