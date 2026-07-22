import "reflect-metadata";

import { NestFactory } from "@nestjs/core";

import { AppModule } from "./app.module.js";
import { validateRuntimeConfig } from "./config/env.js";

validateRuntimeConfig();
await NestFactory.createApplicationContext(AppModule, { bufferLogs: true });
