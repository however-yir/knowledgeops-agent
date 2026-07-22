import { Module } from "@nestjs/common";

import { HistoryModule } from "../history/history.module.js";
import { AiController } from "./ai.controller.js";
import { AiService } from "./ai.service.js";
import { AnswerFeedbackService } from "./answer-feedback.service.js";
import { ChatService } from "./chat.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RagService } from "./rag.service.js";
import { ReactService } from "./react.service.js";
import { RetrievalService } from "./retrieval.service.js";
import { VectorClient } from "./vector.client.js";

@Module({
  imports: [HistoryModule],
  controllers: [AiController],
  providers: [AiService, AnswerFeedbackService, ChatService, RagService, ReactService, RetrievalService, OpenAiCompatibleClient, VectorClient],
  exports: [AiService, ChatService, RagService, ReactService, RetrievalService, OpenAiCompatibleClient, VectorClient]
})
export class AiModule {}
