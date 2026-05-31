import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";

import { env } from "../config/env.js";
import { MetricsService } from "../platform/metrics.service.js";
import { IngestionService } from "./ingestion.service.js";

@Injectable()
export class IngestionWorker implements OnModuleInit, OnModuleDestroy {
  private timer: NodeJS.Timeout | undefined;
  private running = false;

  constructor(
    private readonly ingestionService: IngestionService,
    private readonly metrics: MetricsService
  ) {}

  onModuleInit(): void {
    if (!env.APP_INGESTION_WORKER_ENABLED) {
      return;
    }
    this.timer = setInterval(() => {
      void this.tick();
    }, env.APP_INGESTION_WORKER_INTERVAL_MS);
    this.timer.unref?.();
  }

  onModuleDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }

  async tick(): Promise<number> {
    if (this.running) {
      return 0;
    }
    this.running = true;
    const started = Date.now();
    try {
      const processed = this.ingestionService.processReadyBatch(env.APP_INGESTION_WORKER_CONCURRENCY);
      this.metrics.increment("ingestion_worker_batches_total", { outcome: "success" });
      this.metrics.observe("ingestion_worker_batch_latency_ms", Date.now() - started);
      return processed;
    } catch (error) {
      this.metrics.increment("ingestion_worker_batches_total", { outcome: "error" });
      throw error;
    } finally {
      this.running = false;
    }
  }
}
