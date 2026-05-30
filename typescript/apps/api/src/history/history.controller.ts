import { Controller, Get, Headers, Param, Query } from "@nestjs/common";

import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { HistoryService } from "./history.service.js";

@Controller("ai/history")
export class HistoryController {
  constructor(private readonly historyService: HistoryService) {}

  @Get(":type")
  getChatIds(
    @Headers(TENANT_HEADER) tenantHeader: string | undefined,
    @Param("type") type: string,
    @Query("page") page = "1",
    @Query("pageSize") pageSize = "20"
  ) {
    return this.historyService.listChatIds(normalizeTenant(tenantHeader), type, Number(page), Number(pageSize));
  }

  @Get(":type/:chatId")
  getChatHistory(
    @Headers(TENANT_HEADER) tenantHeader: string | undefined,
    @Param("type") type: string,
    @Param("chatId") chatId: string,
    @Query("page") page = "1",
    @Query("pageSize") pageSize = "50"
  ) {
    return this.historyService.listMessages(normalizeTenant(tenantHeader), type, chatId, Number(page), Number(pageSize));
  }
}
