import { Module } from "@nestjs/common";

import { SessionsController } from "./sessions.controller.js";
import { SessionsService } from "./sessions.service.js";

@Module({
  controllers: [SessionsController],
  providers: [SessionsService],
  exports: [SessionsService]
})
export class SessionsModule {}
