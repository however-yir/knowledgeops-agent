import { Module } from "@nestjs/common";

import { HealthController } from "./health.controller.js";
import { OpenApiController } from "./openapi.controller.js";

@Module({
  controllers: [HealthController, OpenApiController]
})
export class HealthModule {}
