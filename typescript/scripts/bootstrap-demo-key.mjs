import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

if (process.env.APP_BOOTSTRAP_DEMO_KEY !== "true") {
  console.log("demo API key bootstrap disabled");
  process.exit(0);
}
if (!process.env.APP_DEMO_API_KEY?.trim()) {
  console.error("APP_DEMO_API_KEY is required when APP_BOOTSTRAP_DEMO_KEY=true");
  process.exit(1);
}

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const requireFromApi = createRequire(join(root, "apps", "api", "package.json"));
const { PrismaClient } = requireFromApi("@prisma/client");
const prisma = new PrismaClient();
try {
  const now = new Date();
  const keyHash = createHash("sha256").update(process.env.APP_DEMO_API_KEY.trim()).digest("hex");
  await prisma.apiKey.upsert({
    where: { keyHash },
    update: {
      keyName: "ts-bootstrap-admin-key",
      roleName: "ADMIN",
      tenantId: "public",
      enabled: true,
      revokedAt: null,
      updatedAt: now
    },
    create: {
      keyHash,
      keyName: "ts-bootstrap-admin-key",
      roleName: "ADMIN",
      tenantId: "public",
      enabled: true,
      createdAt: now,
      updatedAt: now
    }
  });
  console.log("demo API key bootstrap ok");
} finally {
  await prisma.$disconnect();
}
