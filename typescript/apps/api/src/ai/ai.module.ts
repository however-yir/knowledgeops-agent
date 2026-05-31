import { Module } from "@nestjs/common";

import { HistoryModule } from "../history/history.module.js";
import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RetrievalService } from "./retrieval.service.js";

@Module({
  imports: [HistoryModule],
  controllers: [AiController],
  providers: [AiService, RetrievalService, OpenAiCompatibleClient],
  exports: [AiService, RetrievalService]
})
export class AiModule {}
