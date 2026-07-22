import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { SessionsModule } from "../sessions/sessions.module.js";
import { WorkflowController } from "./workflow.controller.js";
import { WorkflowService } from "./workflow.service.js";

@Module({
  imports: [AiModule, SessionsModule],
  controllers: [WorkflowController],
  providers: [WorkflowService]
})
export class WorkflowModule {}
