import { Module } from "@nestjs/common";

import { AiModule } from "./ai/ai.module.js";
import { HarnessModule } from "./agent/harness.module.js";
import { AuthModule } from "./auth/auth.module.js";
import { EvaluationModule } from "./evaluation/evaluation.module.js";
import { HealthModule } from "./health/health.module.js";
import { IngestionModule } from "./ingestion/ingestion.module.js";
import { OperationsModule } from "./operations/operations.module.js";
import { PlatformModule } from "./platform/platform.module.js";
import { SessionsModule } from "./sessions/sessions.module.js";
import { WorkflowModule } from "./workflow/workflow.module.js";

@Module({
  imports: [
    PlatformModule,
    HealthModule,
    AuthModule,
    AiModule,
    IngestionModule,
    HarnessModule,
    SessionsModule,
    WorkflowModule,
    EvaluationModule,
    OperationsModule
  ]
})
export class AppModule {}
