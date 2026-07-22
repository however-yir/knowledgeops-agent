import { Module } from "@nestjs/common";

import { AiModule } from "../ai/ai.module.js";
import { HarnessController } from "./harness.controller.js";
import { McpClient } from "./mcp.client.js";

@Module({
  imports: [AiModule],
  controllers: [HarnessController],
  providers: [McpClient]
})
export class HarnessModule {}
