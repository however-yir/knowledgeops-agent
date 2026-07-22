import { Injectable, OnModuleDestroy } from "@nestjs/common";
import { Redis } from "ioredis";
import amqp, { type ChannelModel, type ConfirmChannel, type GetMessage } from "amqplib";

import { env } from "../config/env.js";
import type { IngestionJobRecord } from "../platform/platform.store.js";

@Injectable()
export class IngestionQueueService implements OnModuleDestroy {
  private client: Redis | undefined;
  private groupReady = false;
  private rabbitConnection: ChannelModel | undefined;
  private rabbitChannel: ConfirmChannel | undefined;
  private rabbitReady = false;
  private readonly rabbitMessages = new Map<string, GetMessage>();

  async onModuleDestroy(): Promise<void> {
    this.rabbitMessages.clear();
    await this.rabbitChannel?.close().catch(() => undefined);
    await this.rabbitConnection?.close().catch(() => undefined);
    this.client?.disconnect();
  }

  enabled(): boolean {
    return ["redis-stream", "rabbitmq"].includes(this.backend());
  }

  async enqueue(job: IngestionJobRecord): Promise<void> {
    const backend = this.backend();
    if (backend === "in-memory" || backend === "db-polling") {
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
      const accepted = env.APP_RABBITMQ_EXCHANGE
        ? channel.publish(env.APP_RABBITMQ_EXCHANGE, env.APP_RABBITMQ_ROUTING_KEY, payload, { persistent: true })
        : channel.sendToQueue(env.APP_RABBITMQ_QUEUE, payload, { persistent: true });
      if (!accepted) await onceDrain(channel);
      await withTimeout(channel.waitForConfirms(), env.APP_RABBITMQ_CONFIRM_TIMEOUT_MS, "RabbitMQ publish confirm timed out");
      return;
    }
    await this.ensureGroup();
    await this.redis().xadd(env.APP_REDIS_STREAM_KEY, "*", "tenantId", job.tenantId, "jobId", job.jobId);
  }

  async next(limit: number): Promise<Array<{ streamId: string; tenantId: string; jobId: string }>> {
    const backend = this.backend();
    if (backend === "in-memory" || backend === "db-polling") {
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
        const streamId = `rabbit:${message.fields.deliveryTag}`;
        try {
          const payload = parseQueueMessage(message.content.toString("utf8"));
          this.rabbitMessages.set(streamId, message);
          messages.push({ streamId, ...payload });
        } catch {
          channel.nack(message, false, false);
        }
      }
      return messages;
    }
    await this.ensureGroup();
    const reclaimed = await this.reclaimRedis(limit);
    if (reclaimed.length > 0) return reclaimed;
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
    const valid: Array<{ streamId: string; tenantId: string; jobId: string }> = [];
    for (const [streamId, fields] of messages) {
      try {
        valid.push({ streamId, ...parseQueueRecord(fieldsToRecord(fields)) });
      } catch {
        await this.redis().xack(env.APP_REDIS_STREAM_KEY, env.APP_REDIS_CONSUMER_GROUP, streamId);
      }
    }
    return valid;
  }

  async ack(streamId: string): Promise<void> {
    const backend = this.backend();
    if (backend === "in-memory" || backend === "db-polling") {
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
    if (backend === "in-memory" || backend === "db-polling") {
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
      const accepted = env.APP_RABBITMQ_DLQ_EXCHANGE
        ? channel.publish(env.APP_RABBITMQ_DLQ_EXCHANGE, env.APP_RABBITMQ_DLQ_ROUTING_KEY, body, { persistent: true })
        : channel.sendToQueue(env.APP_RABBITMQ_DLQ_QUEUE, body, { persistent: true });
      if (!accepted) await onceDrain(channel);
      await withTimeout(channel.waitForConfirms(), env.APP_RABBITMQ_CONFIRM_TIMEOUT_MS, "RabbitMQ DLQ publish confirm timed out");
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

  private async rabbit(): Promise<ConfirmChannel> {
    if (this.rabbitChannel && this.rabbitReady) {
      return this.rabbitChannel;
    }
    this.rabbitConnection ??= await amqp.connect(env.APP_RABBITMQ_URL);
    this.rabbitConnection.once("close", () => {
      this.rabbitReady = false;
      this.rabbitChannel = undefined;
      this.rabbitConnection = undefined;
      this.rabbitMessages.clear();
    });
    this.rabbitChannel ??= await this.rabbitConnection.createConfirmChannel();
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

  private backend(): "in-memory" | "db-polling" | "redis-stream" | "rabbitmq" {
    const value = env.APP_INGESTION_QUEUE_BACKEND.replace("_", "-").toLowerCase();
    if (value === "db-polling") return "db-polling";
    if (value === "redis-stream") return "redis-stream";
    if (value === "rabbitmq") return "rabbitmq";
    return "in-memory";
  }

  private async reclaimRedis(limit: number): Promise<Array<{ streamId: string; tenantId: string; jobId: string }>> {
    const response = await this.redis().xautoclaim(
      env.APP_REDIS_STREAM_KEY,
      env.APP_REDIS_CONSUMER_GROUP,
      env.APP_REDIS_CONSUMER_NAME,
      env.APP_INGESTION_CLAIM_IDLE_MS,
      "0-0",
      "COUNT",
      Math.max(1, limit)
    ) as [string, Array<[string, string[]]>];
    const valid: Array<{ streamId: string; tenantId: string; jobId: string }> = [];
    for (const [streamId, fields] of response[1] ?? []) {
      try {
        valid.push({ streamId, ...parseQueueRecord(fieldsToRecord(fields)) });
      } catch {
        await this.redis().xack(env.APP_REDIS_STREAM_KEY, env.APP_REDIS_CONSUMER_GROUP, streamId);
      }
    }
    return valid;
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

function parseQueueMessage(value: string): { tenantId: string; jobId: string } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("invalid queue message JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid queue message payload");
  return parseQueueRecord(parsed as Record<string, unknown>);
}

function parseQueueRecord(value: Record<string, unknown>): { tenantId: string; jobId: string } {
  const tenantId = typeof value.tenantId === "string" ? value.tenantId.trim() : "";
  const jobId = typeof value.jobId === "string" ? value.jobId.trim() : "";
  if (!tenantId || !jobId) throw new Error("queue message requires tenantId and jobId");
  return { tenantId, jobId };
}

function onceDrain(channel: { once(event: "drain", listener: () => void): unknown }): Promise<void> {
  return new Promise((resolve) => channel.once("drain", resolve));
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
      })
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
