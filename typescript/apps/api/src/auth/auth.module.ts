import { MiddlewareConsumer, Module, NestModule } from "@nestjs/common";
import { APP_GUARD } from "@nestjs/core";

import { AuditLogMiddleware } from "./audit.middleware.js";
import { AuthController } from "./auth.controller.js";
import { AuthGuard } from "./auth.guard.js";
import { AuthContextMiddleware } from "./auth.middleware.js";
import { AuthService } from "./auth.service.js";
import { HttpMetricsMiddleware } from "./http-metrics.middleware.js";
import { RateLimitMiddleware } from "./rate-limit.middleware.js";
import { SecurityHeadersMiddleware } from "./security-headers.middleware.js";

@Module({
  controllers: [AuthController],
  providers: [
    AuthService,
    AuthContextMiddleware,
    AuditLogMiddleware,
    HttpMetricsMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    {
      provide: APP_GUARD,
      useClass: AuthGuard
    }
  ]
})
export class AuthModule implements NestModule {
  configure(consumer: MiddlewareConsumer): void {
    consumer.apply(SecurityHeadersMiddleware, AuthContextMiddleware, HttpMetricsMiddleware, RateLimitMiddleware, AuditLogMiddleware).forRoutes("*");
  }
}
