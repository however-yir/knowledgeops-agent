import { Global, Module } from "@nestjs/common";

import { PlatformStore } from "./platform.store.js";

@Global()
@Module({
  providers: [PlatformStore],
  exports: [PlatformStore]
})
export class PlatformModule {}
