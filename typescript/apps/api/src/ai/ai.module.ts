import { Module } from "@nestjs/common";

import { HistoryModule } from "../history/history.module.js";
import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";
import { RetrievalService } from "./retrieval.service.js";

@Module({
  imports: [HistoryModule],
  controllers: [AiController],
  providers: [AiService, RetrievalService],
  exports: [AiService, RetrievalService]
})
export class AiModule {}
