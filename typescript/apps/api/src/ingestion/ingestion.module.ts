import { Module } from "@nestjs/common";

import { IngestionController } from "./ingestion.controller.js";
import { IngestionService } from "./ingestion.service.js";

@Module({
  controllers: [IngestionController],
  providers: [IngestionService],
  exports: [IngestionService]
})
export class IngestionModule {}
