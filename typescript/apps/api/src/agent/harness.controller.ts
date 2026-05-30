import { Body, Controller, Get, Param, Post } from "@nestjs/common";

import { newId } from "../common/ids.js";
import { PlatformStore } from "../platform/platform.store.js";

@Controller("ai/harness")
export class HarnessController {
  constructor(private readonly store: PlatformStore) {}

  @Get("actions")
  actions() {
    return [
      {
        action: "workspace_read_file",
        runtime: "workspace",
        requiredKeys: ["path"],
        optionalKeys: ["maxBytes"],
        riskLevel: "read",
        trustedOnly: true
      },
      {
        action: "rag_query",
        runtime: "retrieval",
        requiredKeys: ["query"],
        optionalKeys: ["chatId"],
        riskLevel: "read",
        trustedOnly: false
      }
    ];
  }

  @Post("actions/preview")
  preview(@Body() request: Record<string, unknown>) {
    const token = newId("ta");
    this.store.trustedActions.set(token, request);
    return {
      ok: 1,
      token,
      action: request.action ?? "unknown",
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
      preview: { status: "pending_confirmation", request }
    };
  }

  @Post("actions/execute/:token")
  execute(@Param("token") token: string) {
    const request = this.store.trustedActions.get(token);
    if (!request) {
      return { status: "not_found", source: "trusted-action" };
    }
    this.store.trustedActions.delete(token);
    return {
      status: "executed",
      source: "trusted-action",
      action: request.action ?? "unknown",
      observation: { ok: true }
    };
  }
}
