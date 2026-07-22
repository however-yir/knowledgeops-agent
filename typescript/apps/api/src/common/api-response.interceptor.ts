import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import { mergeMap, type Observable } from "rxjs";

import { PlatformStore } from "../platform/platform.store.js";
import { tenantIdFromRequest } from "./request-context.js";
import { traceIdFrom } from "./trace.js";

@Injectable()
export class ApiResponseInterceptor implements NestInterceptor {
  constructor(private readonly store: PlatformStore) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<FastifyRequest>();
    const response = context.switchToHttp().getResponse<{ header?: (name: string, value: string) => unknown }>();
    response.header?.("X-Trace-ID", traceIdFrom(request));
    response.header?.("X-Tenant-ID", tenantIdFromRequest(request));
    return next.handle().pipe(mergeMap(async (value) => {
      await this.store.waitForPersistence();
      return value;
    }));
  }
}
