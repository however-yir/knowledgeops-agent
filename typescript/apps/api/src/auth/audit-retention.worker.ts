import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";

import { env } from "../config/env.js";
import { MetricsService } from "../platform/metrics.service.js";
import { PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class AuditRetentionWorker implements OnModuleInit, OnModuleDestroy {
  private timer: NodeJS.Timeout | undefined;

  constructor(
    private readonly store: PlatformStore,
    private readonly metrics: MetricsService
  ) {}

  onModuleInit(): void {
    if (!env.APP_AUDIT_RETENTION_WORKER_ENABLED) {
      return;
    }
    this.timer = setInterval(() => this.cleanup(), env.APP_AUDIT_RETENTION_INTERVAL_MS);
    this.timer.unref?.();
  }

  onModuleDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }

  cleanup(): number {
    const cutoff = Date.now() - env.APP_AUDIT_RETENTION_DAYS * 24 * 60 * 60 * 1000;
    const before = this.store.auditLogs.length;
    for (let index = this.store.auditLogs.length - 1; index >= 0; index -= 1) {
      const createdAt = String(this.store.auditLogs[index].createdAt ?? "");
      if (createdAt && Date.parse(createdAt) < cutoff) {
        this.store.auditLogs.splice(index, 1);
      }
    }
    const removed = before - this.store.auditLogs.length;
    if (removed > 0) {
      this.metrics.increment("audit_retention_deleted_total", {}, removed);
      this.store.persist();
    }
    return removed;
  }
}
