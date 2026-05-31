import { Injectable } from "@nestjs/common";
import { Redis } from "ioredis";
import amqp from "amqplib";

import { env } from "../config/env.js";
import type { IngestionJobRecord } from "../platform/platform.store.js";

@Injectable()
export class IngestionQueueService {
  private client: Redis | undefined;
  private groupReady = false;
  private rabbitConnection: any;
  private rabbitChannel: any;
  private rabbitReady = false;
  private readonly rabbitMessages = new Map<string, any>();

  enabled(): boolean {
    return this.backend() !== "in-memory";
  }

  async enqueue(job: IngestionJobRecord): Promise<void> {
    const backend = this.backend();
    if (backend === "in-memory") {
      return;
    }
    if (backend === "rabbitmq") {
      const channel = await this.rabbit();
      const payload = Buffer.from(JSON.stringify({
        tenantId: job.tenantId,
        jobId: job.jobId,
        traceId: job.traceId ?? "",
        publishedAt: Date.now()
      }));
      if (env.APP_RABBITMQ_EXCHANGE) {
        channel.publish(env.APP_RABBITMQ_EXCHANGE, env.APP_RABBITMQ_ROUTING_KEY, payload, { persistent: true });
      } else {
        channel.sendToQueue(env.APP_RABBITMQ_QUEUE, payload, { persistent: true });
      }
      return;
    }
    await this.ensureGroup();
    await this.redis().xadd(env.APP_REDIS_STREAM_KEY, "*", "tenantId", job.tenantId, "jobId", job.jobId);
  }

  async next(limit: number): Promise<Array<{ streamId: string; tenantId: string; jobId: string }>> {
    const backend = this.backend();
    if (backend === "in-memory") {
      return [];
    }
    if (backend === "rabbitmq") {
      const channel = await this.rabbit();
      const messages: Array<{ streamId: string; tenantId: string; jobId: string }> = [];
      for (let index = 0; index < limit; index += 1) {
        const message = await channel.get(env.APP_RABBITMQ_QUEUE, { noAck: false });
        if (!message) {
          break;
        }
        const payload = parseJson(message.content.toString("utf8"));
        const streamId = `rabbit:${message.fields.deliveryTag}`;
        this.rabbitMessages.set(streamId, message);
        messages.push({
          streamId,
          tenantId: String(payload.tenantId ?? "public"),
          jobId: String(payload.jobId ?? "")
        });
      }
      return messages.filter((message) => message.jobId);
    }
    await this.ensureGroup();
    const response = await this.redis().xreadgroup(
      "GROUP",
      env.APP_REDIS_CONSUMER_GROUP,
      env.APP_REDIS_CONSUMER_NAME,
      "COUNT",
      limit,
      "BLOCK",
      50,
      "STREAMS",
      env.APP_REDIS_STREAM_KEY,
      ">"
    );
    const streams = response as Array<[string, Array<[string, string[]]>]> | null;
    const messages = streams?.[0]?.[1] ?? [];
    return messages.map(([streamId, fields]: [string, string[]]) => {
      const data = fieldsToRecord(fields);
      return { streamId, tenantId: data.tenantId ?? "public", jobId: data.jobId ?? "" };
    }).filter((item: { streamId: string; tenantId: string; jobId: string }) => item.jobId);
  }

  async ack(streamId: string): Promise<void> {
    const backend = this.backend();
    if (backend === "in-memory") {
      return;
    }
    if (backend === "rabbitmq") {
      const message = this.rabbitMessages.get(streamId);
      if (message) {
        (await this.rabbit()).ack(message);
        this.rabbitMessages.delete(streamId);
      }
      return;
    }
    await this.redis().xack(env.APP_REDIS_STREAM_KEY, env.APP_REDIS_CONSUMER_GROUP, streamId);
  }

  async publishDlq(job: IngestionJobRecord, reason: string): Promise<void> {
    const backend = this.backend();
    if (backend === "in-memory") {
      return;
    }
    const payload = {
      tenantId: job.tenantId,
      jobId: job.jobId,
      traceId: job.traceId ?? "",
      reason,
      publishedAt: Date.now()
    };
    if (backend === "rabbitmq") {
      const channel = await this.rabbit();
      const body = Buffer.from(JSON.stringify(payload));
      if (env.APP_RABBITMQ_DLQ_EXCHANGE) {
        channel.publish(env.APP_RABBITMQ_DLQ_EXCHANGE, env.APP_RABBITMQ_DLQ_ROUTING_KEY, body, { persistent: true });
      } else {
        channel.sendToQueue(env.APP_RABBITMQ_DLQ_QUEUE, body, { persistent: true });
      }
      return;
    }
    await this.redis().xadd(
      env.APP_REDIS_DLQ_STREAM_KEY,
      "*",
      "tenantId",
      payload.tenantId,
      "jobId",
      payload.jobId,
      "traceId",
      payload.traceId,
      "reason",
      payload.reason
    );
  }

  private redis(): Redis {
    this.client ??= new Redis(env.APP_REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 2 });
    return this.client;
  }

  private async rabbit(): Promise<any> {
    if (this.rabbitChannel && this.rabbitReady) {
      return this.rabbitChannel;
    }
    this.rabbitConnection ??= await amqp.connect(env.APP_RABBITMQ_URL);
    this.rabbitChannel ??= await this.rabbitConnection.createChannel();
    await this.rabbitChannel.assertQueue(env.APP_RABBITMQ_QUEUE, { durable: true });
    if (env.APP_RABBITMQ_EXCHANGE) {
      await this.rabbitChannel.assertExchange(env.APP_RABBITMQ_EXCHANGE, "direct", { durable: true });
      await this.rabbitChannel.bindQueue(env.APP_RABBITMQ_QUEUE, env.APP_RABBITMQ_EXCHANGE, env.APP_RABBITMQ_ROUTING_KEY);
    }
    await this.rabbitChannel.assertQueue(env.APP_RABBITMQ_DLQ_QUEUE, { durable: true });
    if (env.APP_RABBITMQ_DLQ_EXCHANGE) {
      await this.rabbitChannel.assertExchange(env.APP_RABBITMQ_DLQ_EXCHANGE, "direct", { durable: true });
      await this.rabbitChannel.bindQueue(env.APP_RABBITMQ_DLQ_QUEUE, env.APP_RABBITMQ_DLQ_EXCHANGE, env.APP_RABBITMQ_DLQ_ROUTING_KEY);
    }
    this.rabbitReady = true;
    return this.rabbitChannel;
  }

  private backend(): "in-memory" | "redis-stream" | "rabbitmq" {
    const value = env.APP_INGESTION_QUEUE_BACKEND.replace("_", "-").toLowerCase();
    if (value === "redis-stream") {
      return "redis-stream";
    }
    if (value === "rabbitmq") {
      return "rabbitmq";
    }
    return "in-memory";
  }

  private async ensureGroup(): Promise<void> {
    if (this.groupReady) {
      return;
    }
    try {
      await this.redis().xgroup("CREATE", env.APP_REDIS_STREAM_KEY, env.APP_REDIS_CONSUMER_GROUP, "$", "MKSTREAM");
    } catch (error) {
      if (!String(error).includes("BUSYGROUP")) {
        throw error;
      }
    }
    this.groupReady = true;
  }
}

function fieldsToRecord(fields: string[]): Record<string, string> {
  const record: Record<string, string> = {};
  for (let index = 0; index < fields.length; index += 2) {
    record[fields[index]] = fields[index + 1] ?? "";
  }
  return record;
}

function parseJson(value: string): Record<string, unknown> {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return {};
  }
}
