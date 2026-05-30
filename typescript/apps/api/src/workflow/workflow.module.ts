import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { WorkflowController } from "./workflow.controller.js";
import { WorkflowService } from "./workflow.service.js";

@Module({
  imports: [AiModule],
  controllers: [WorkflowController],
  providers: [WorkflowService]
})
export class WorkflowModule {}
