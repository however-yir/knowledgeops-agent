import { Module } from "@nestjs/common";

import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";

@Module({
  controllers: [AiController],
  providers: [AiService],
  exports: [AiService]
})
export class AiModule {}
