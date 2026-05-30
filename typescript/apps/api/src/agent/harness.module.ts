import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { HarnessController } from "./harness.controller.js";

@Module({
  imports: [AiModule],
  controllers: [HarnessController]
})
export class HarnessModule {}
