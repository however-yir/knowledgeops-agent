import { Injectable } from "@nestjs/common";

import { PlatformStore } from "./platform.store.js";

@Injectable()
export class MetricsService {
  constructor(private readonly store: PlatformStore) {}

  increment(name: string, labels: Record<string, string | number | boolean | undefined> = {}, value = 1): void {
    this.store.incrementMetric(name, labels, value);
  }

  observe(name: string, value: number, labels: Record<string, string | number | boolean | undefined> = {}): void {
    for (const bucket of [50, 100, 250, 500, 1000, 2500, 5000, Number.POSITIVE_INFINITY]) {
      if (value <= bucket) {
        this.store.incrementMetric(`${name}_bucket`, { ...labels, le: bucket === Number.POSITIVE_INFINITY ? "+Inf" : bucket }, 1);
      }
    }
    this.store.incrementMetric(`${name}_count`, labels, 1);
    this.store.incrementMetric(`${name}_sum`, labels, value);
  }

  prometheus(): string {
    return [...this.store.metrics.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, value]) => `${key} ${value}`)
      .join("\n") + "\n";
  }
}
