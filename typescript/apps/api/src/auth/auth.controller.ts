import { Body, Controller, Headers, Post, Query } from "@nestjs/common";

import { TENANT_HEADER } from "../common/tenant.js";
import { AuthService } from "./auth.service.js";

@Controller("auth")
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Post("token")
  token(@Headers("x-api-key") apiKey: string | undefined, @Headers(TENANT_HEADER) tenantId: string | undefined) {
    return this.authService.exchangeApiKey(apiKey, tenantId);
  }

  @Post("refresh")
  refresh(
    @Headers("authorization") authorization: string | undefined,
    @Headers("x-refresh-token") refreshToken: string | undefined,
    @Body() body?: { refreshToken?: string }
  ) {
    const bearer = authorization?.startsWith("Bearer ") ? authorization.slice("Bearer ".length) : undefined;
    return this.authService.refresh(body?.refreshToken ?? bearer ?? refreshToken);
  }

  @Post("api-keys")
  issueApiKey(@Query("keyName") keyName = "ts-issued-key", @Query("role") role = "USER", @Query("tenantId") tenantId?: string) {
    return this.authService.issueApiKey(keyName, role, tenantId);
  }

  @Post("api-keys/rotate")
  rotateApiKey(@Query("keyName") keyName: string, @Query("role") role = "USER", @Query("tenantId") tenantId?: string) {
    return this.authService.rotateApiKey(keyName, role, tenantId);
  }

  @Post("api-keys/revoke")
  revokeApiKey(@Query("keyName") keyName: string, @Query("tenantId") tenantId?: string, @Body() _body?: unknown) {
    return this.authService.revokeApiKey(keyName, tenantId);
  }
}
