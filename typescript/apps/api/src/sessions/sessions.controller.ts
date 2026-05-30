import { Body, Controller, Get, Param, Post, Put, Query } from "@nestjs/common";
import type { SessionState } from "@knowledgeops/shared";

import { SessionsService } from "./sessions.service.js";

@Controller("ai/sessions")
export class SessionsController {
  constructor(private readonly sessionsService: SessionsService) {}

  @Get()
  list(@Query("page") page = "1", @Query("pageSize") pageSize = "20", @Query("includeArchived") includeArchived = "false") {
    return this.sessionsService.list(Number(page), Number(pageSize), includeArchived === "true");
  }

  @Get(":sessionId")
  get(@Param("sessionId") sessionId: string) {
    return this.sessionsService.get(sessionId);
  }

  @Put(":sessionId")
  upsert(@Param("sessionId") sessionId: string, @Body() payload: SessionState) {
    return this.sessionsService.upsert(sessionId, payload);
  }

  @Post(":sessionId/pin")
  pin(@Param("sessionId") sessionId: string, @Query("value") value: string) {
    return this.sessionsService.setPinned(sessionId, value === "true");
  }

  @Post(":sessionId/archive")
  archive(@Param("sessionId") sessionId: string, @Query("value") value: string) {
    return this.sessionsService.setArchived(sessionId, value === "true");
  }

  @Post(":sessionId/branches/compare")
  compare(@Param("sessionId") sessionId: string, @Body() body: { sourceBranchId: string; targetBranchId: string }) {
    return this.sessionsService.compare(sessionId, body.sourceBranchId, body.targetBranchId);
  }

  @Post(":sessionId/branches/merge")
  merge(@Param("sessionId") sessionId: string, @Body() body: { sourceBranchId: string; targetBranchId: string; title?: string }) {
    return this.sessionsService.merge(sessionId, body.sourceBranchId, body.targetBranchId, body.title);
  }
}
