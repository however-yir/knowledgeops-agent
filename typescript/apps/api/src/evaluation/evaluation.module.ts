import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { EvaluationController } from "./evaluation.controller.js";

@Module({
  imports: [AiModule],
  controllers: [EvaluationController]
})
export class EvaluationModule {}
