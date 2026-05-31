import { Injectable, NestMiddleware } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ServerResponse } from "node:http";

@Injectable()
export class SecurityHeadersMiddleware implements NestMiddleware {
  use(_req: FastifyRequest, res: FastifyReply | ServerResponse, next: () => void): void {
    const raw = "raw" in res ? res.raw : res;
    raw.setHeader("X-Content-Type-Options", "nosniff");
    raw.setHeader("X-Frame-Options", "DENY");
    raw.setHeader("Referrer-Policy", "no-referrer");
    raw.setHeader("Permissions-Policy", "geolocation=(), microphone=(), camera=()");
    raw.setHeader("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
    next();
  }
}
