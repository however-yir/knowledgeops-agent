import { Injectable } from "@nestjs/common";
import { Redis } from "ioredis";

import { env } from "../config/env.js";
import type { IngestionJobRecord } from "../platform/platform.store.js";

@Injectable()
export class IngestionQueueService {
  private client: Redis | undefined;
  private groupReady = false;

  enabled(): boolean {
    return env.APP_INGESTION_QUEUE_BACKEND === "redis-stream";
  }

  async enqueue(job: IngestionJobRecord): Promise<void> {
    if (!this.enabled()) {
      return;
    }
    await this.ensureGroup();
    await this.redis().xadd(env.APP_REDIS_STREAM_KEY, "*", "tenantId", job.tenantId, "jobId", job.jobId);
  }

  async next(limit: number): Promise<Array<{ streamId: string; tenantId: string; jobId: string }>> {
    if (!this.enabled()) {
      return [];
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
    if (!this.enabled()) {
      return;
    }
    await this.redis().xack(env.APP_REDIS_STREAM_KEY, env.APP_REDIS_CONSUMER_GROUP, streamId);
  }

  private redis(): Redis {
    this.client ??= new Redis(env.APP_REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 2 });
    return this.client;
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
