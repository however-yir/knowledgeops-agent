import { Module } from "@nestjs/common";

import { OperationsController } from "./operations.controller.js";

@Module({
  controllers: [OperationsController]
})
export class OperationsModule {}
