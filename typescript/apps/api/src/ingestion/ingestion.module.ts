import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { HistoryModule } from "../history/history.module.js";
import { IngestionController } from "./ingestion.controller.js";
import { IngestionService } from "./ingestion.service.js";

@Module({
  imports: [AiModule, HistoryModule],
  controllers: [IngestionController],
  providers: [IngestionService],
  exports: [IngestionService]
})
export class IngestionModule {}
