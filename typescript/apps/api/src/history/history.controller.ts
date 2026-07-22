import { Controller, Get, Param, Query } from "@nestjs/common";

import { TenantId } from "../common/tenant-id.decorator.js";
import { HistoryService } from "./history.service.js";

@Controller("ai/history")
export class HistoryController {
  constructor(private readonly historyService: HistoryService) {}

  @Get(":type")
  getChatIds(
    @TenantId() tenantId: string,
    @Param("type") type: string,
    @Query("page") page = "1",
    @Query("pageSize") pageSize = "20"
  ) {
    return this.historyService.listChatIds(tenantId, type, Number(page), Number(pageSize));
  }

  @Get(":type/:chatId")
  getChatHistory(
    @TenantId() tenantId: string,
    @Param("type") type: string,
    @Param("chatId") chatId: string,
    @Query("page") page = "1",
    @Query("pageSize") pageSize = "50"
  ) {
    return this.historyService.listMessages(tenantId, type, chatId, Number(page), Number(pageSize));
  }
}
