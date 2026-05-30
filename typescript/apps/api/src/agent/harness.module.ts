import { Module } from "@nestjs/common";

import { HarnessController } from "./harness.controller.js";

@Module({
  controllers: [HarnessController]
})
export class HarnessModule {}
