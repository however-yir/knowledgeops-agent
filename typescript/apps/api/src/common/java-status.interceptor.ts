import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from "@nestjs/common";
import type { Observable } from "rxjs";

@Injectable()
export class JavaStatusInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<{ method?: string }>();
    const response = context.switchToHttp().getResponse<{ status?: (code: number) => unknown; statusCode?: number }>();
    if (request.method?.toUpperCase() === "POST" && response.statusCode === 201 && typeof response.status === "function") {
      response.status(200);
    }
    return next.handle();
  }
}
