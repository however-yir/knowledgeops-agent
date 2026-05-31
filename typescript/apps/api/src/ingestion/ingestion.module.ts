import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { HistoryModule } from "../history/history.module.js";
import { IngestionController } from "./ingestion.controller.js";
import { IngestionQueueService } from "./ingestion.queue.js";
import { IngestionService } from "./ingestion.service.js";
import { IngestionWorker } from "./ingestion.worker.js";

@Module({
  imports: [AiModule, HistoryModule],
  controllers: [IngestionController],
  providers: [IngestionService, IngestionQueueService, IngestionWorker],
  exports: [IngestionService]
})
export class IngestionModule {}
