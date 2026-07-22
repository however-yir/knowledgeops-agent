import { Module } from "@nestjs/common";

import { HistoryModule } from "../history/history.module.js";
import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";
import { AnswerFeedbackService } from "./answer-feedback.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RetrievalService } from "./retrieval.service.js";
import { VectorClient } from "./vector.client.js";

@Module({
  imports: [HistoryModule],
  controllers: [AiController],
  providers: [AiService, AnswerFeedbackService, RetrievalService, OpenAiCompatibleClient, VectorClient],
  exports: [AiService, RetrievalService, OpenAiCompatibleClient, VectorClient]
})
export class AiModule {}
