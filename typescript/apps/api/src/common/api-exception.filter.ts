import { ArgumentsHost, Catch, ExceptionFilter, HttpException, HttpStatus } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";

import { traceIdFrom } from "./trace.js";

@Catch()
export class ApiExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost): void {
    const http = host.switchToHttp();
    const request = http.getRequest<FastifyRequest>();
    const reply = http.getResponse<FastifyReply>();
    const status = exception instanceof HttpException ? exception.getStatus() : HttpStatus.INTERNAL_SERVER_ERROR;
    const traceId = traceIdFrom(request);
    reply.header("X-Trace-ID", traceId);
    reply.status(status).send({
      ok: 0,
      msg: messageFrom(exception),
      code: codeFrom(exception, status),
      traceId
    });
  }
}

function messageFrom(exception: unknown): string {
  if (exception instanceof HttpException) {
    const response = exception.getResponse();
    if (typeof response === "string") {
      return response;
    }
    if (isRecord(response)) {
      const message = response.message;
      if (Array.isArray(message)) {
        return message.join("; ");
      }
      if (typeof message === "string") {
        return message;
      }
    }
  }
  return exception instanceof Error ? exception.message : "internal server error";
}

function codeFrom(exception: unknown, status: number): string {
  if (exception instanceof HttpException) {
    const response = exception.getResponse();
    if (isRecord(response) && typeof response.code === "string") {
      return response.code;
    }
  }
  return status === HttpStatus.UNAUTHORIZED
    ? "UNAUTHORIZED"
    : status === HttpStatus.FORBIDDEN
      ? "FORBIDDEN"
      : status === HttpStatus.NOT_FOUND
        ? "NOT_FOUND"
        : status >= 500
          ? "INTERNAL_ERROR"
          : "BAD_REQUEST";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
