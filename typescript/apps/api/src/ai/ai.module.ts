import { Module } from "@nestjs/common";

import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";
import { RetrievalService } from "./retrieval.service.js";

@Module({
  controllers: [AiController],
  providers: [AiService, RetrievalService],
  exports: [AiService, RetrievalService]
})
export class AiModule {}
