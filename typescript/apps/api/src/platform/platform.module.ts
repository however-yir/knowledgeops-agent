import { Global, Module } from "@nestjs/common";

import { MetricsService } from "./metrics.service.js";
import { ModelRouterService } from "./model-router.service.js";
import { PlatformStore } from "./platform.store.js";
import { PrismaPersistenceService } from "./prisma.persistence.service.js";
import { TenantCostService } from "./tenant-cost.service.js";
import { BusinessToolsService } from "./business-tools.service.js";

@Global()
@Module({
  providers: [PlatformStore, MetricsService, ModelRouterService, TenantCostService, PrismaPersistenceService, BusinessToolsService],
  exports: [PlatformStore, MetricsService, ModelRouterService, TenantCostService, BusinessToolsService]
})
export class PlatformModule {}
