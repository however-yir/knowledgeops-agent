import { Module } from "@nestjs/common";

import { EvaluationController } from "./evaluation.controller.js";

@Module({
  controllers: [EvaluationController]
})
export class EvaluationModule {}
