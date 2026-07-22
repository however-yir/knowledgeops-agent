import { Body, Controller, Get, Param, Post, Put, Query } from "@nestjs/common";
import type { SessionState } from "@knowledgeops/shared";

import { TenantId } from "../common/tenant-id.decorator.js";
import { SessionsService } from "./sessions.service.js";

@Controller("ai/sessions")
export class SessionsController {
  constructor(private readonly sessionsService: SessionsService) {}

  @Get()
  list(
    @TenantId() tenantId: string,
    @Query("page") page = "1",
    @Query("pageSize") pageSize = "20",
    @Query("includeArchived") includeArchived = "false",
    @Query("search") search?: string,
    @Query("workspace") workspace?: string
  ) {
    return this.sessionsService.list(tenantId, Number(page), Number(pageSize), includeArchived === "true", search, workspace);
  }

  @Get(":sessionId")
  get(@TenantId() tenantId: string, @Param("sessionId") sessionId: string) {
    return this.sessionsService.get(tenantId, sessionId);
  }

  @Put(":sessionId")
  upsert(@TenantId() tenantId: string, @Param("sessionId") sessionId: string, @Body() payload: SessionState) {
    return this.sessionsService.upsert(tenantId, sessionId, payload);
  }

  @Post(":sessionId/pin")
  pin(@TenantId() tenantId: string, @Param("sessionId") sessionId: string, @Query("value") value: string) {
    return this.sessionsService.setPinned(tenantId, sessionId, value === "true");
  }

  @Post(":sessionId/archive")
  archive(@TenantId() tenantId: string, @Param("sessionId") sessionId: string, @Query("value") value: string) {
    return this.sessionsService.setArchived(tenantId, sessionId, value === "true");
  }

  @Post(":sessionId/branches/compare")
  compare(
    @TenantId() tenantId: string,
    @Param("sessionId") sessionId: string,
    @Body() body: { sourceBranchId: string; targetBranchId: string }
  ) {
    return this.sessionsService.compare(tenantId, sessionId, body.sourceBranchId, body.targetBranchId);
  }

  @Post(":sessionId/branches/merge")
  merge(
    @TenantId() tenantId: string,
    @Param("sessionId") sessionId: string,
    @Body() body: { sourceBranchId: string; targetBranchId: string; title?: string }
  ) {
    return this.sessionsService.merge(tenantId, sessionId, body.sourceBranchId, body.targetBranchId, body.title);
  }
}
