import { Injectable } from "@nestjs/common";

import { PlatformStore } from "./platform.store.js";

@Injectable()
export class MetricsService {
  constructor(private readonly store: PlatformStore) {}

  increment(name: string, labels: Record<string, string | number | boolean | undefined> = {}, value = 1): void {
    this.store.incrementMetric(name, labels, value);
  }

  prometheus(): string {
    return [...this.store.metrics.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, value]) => `${key} ${value}`)
      .join("\n") + "\n";
  }
}
