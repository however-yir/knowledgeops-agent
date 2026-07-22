import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { EvaluationReportRenderer } from "./evaluation-report.renderer.js";
import { EvaluationController } from "./evaluation.controller.js";
import { EvaluationScorer } from "./evaluation.scorer.js";
import { EvaluationService } from "./evaluation.service.js";

@Module({
  imports: [AiModule],
  controllers: [EvaluationController],
  providers: [EvaluationService, EvaluationScorer, EvaluationReportRenderer]
})
export class EvaluationModule {}
