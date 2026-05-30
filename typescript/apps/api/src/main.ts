import "reflect-metadata";

import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import { NestFactory } from "@nestjs/core";
import { FastifyAdapter, NestFastifyApplication } from "@nestjs/platform-fastify";

import { AppModule } from "./app.module.js";
import { JavaStatusInterceptor } from "./common/java-status.interceptor.js";
import { env } from "./config/env.js";

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create<NestFastifyApplication>(AppModule, new FastifyAdapter(), {
    bufferLogs: true
  });

  app.useGlobalInterceptors(new JavaStatusInterceptor());

  const origins = env.APP_CORS_ALLOWED_ORIGINS.split(",").map((origin) => origin.trim()).filter(Boolean);
  await app.register(cors, {
    origin: origins,
    credentials: true
  });
  await app.register(multipart);

  await app.listen({ host: "0.0.0.0", port: env.PORT });
}

await bootstrap();
