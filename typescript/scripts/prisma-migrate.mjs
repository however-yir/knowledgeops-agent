import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

if (!process.env.DATABASE_URL?.trim()) {
  console.error("DATABASE_URL is required for database migration");
  process.exit(1);
}

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiDir = join(root, "apps", "api");
const schemaPath = join(root, "prisma", "schema.prisma");
const requireFromApi = createRequire(join(apiDir, "package.json"));
const { PrismaClient } = requireFromApi("@prisma/client");
const prismaCliPath = requireFromApi.resolve("prisma/build/index.js");
const javaMigrations = [
  "0001_java_v1",
  "0002_java_v2",
  "0003_java_v4",
  "0004_java_v5",
  "0005_java_v6",
  "0006_java_v7",
  "0007_java_v8",
  "0008_java_v9",
  "0009_java_v10",
  "0010_java_v11",
  "0011_java_v12",
  "0012_java_v13",
  "0013_java_v14"
];

const prisma = new PrismaClient();
try {
  await prisma.$connect();
  const [tables] = await prisma.$queryRawUnsafe(`
    SELECT COUNT(*) AS count_value
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name NOT IN ('_prisma_migrations')
  `);
  const hasApplicationTables = Number(tables?.count_value ?? 0) > 0;
  const [prismaHistory] = await prisma.$queryRawUnsafe(`
    SELECT COUNT(*) AS count_value
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = '_prisma_migrations'
  `);

  if (hasApplicationTables && Number(prismaHistory?.count_value ?? 0) === 0) {
    const [flywayTable] = await prisma.$queryRawUnsafe(`
      SELECT COUNT(*) AS count_value
      FROM information_schema.tables
      WHERE table_schema = DATABASE() AND table_name = 'flyway_schema_history'
    `);
    if (Number(flywayTable?.count_value ?? 0) === 0) {
      throw new Error("non-empty database is not managed by Flyway or Prisma; refusing automatic baseline");
    }
    const [flywayVersion] = await prisma.$queryRawUnsafe(`
      SELECT version
      FROM flyway_schema_history
      WHERE success = 1 AND version IS NOT NULL
      ORDER BY installed_rank DESC
      LIMIT 1
    `);
    if (Number.parseInt(String(flywayVersion?.version ?? "0"), 10) < 14) {
      throw new Error(`Java database must be migrated through V14 before TypeScript baseline; found ${flywayVersion?.version ?? "none"}`);
    }
    for (const migration of javaMigrations) {
      runPrisma(apiDir, ["migrate", "resolve", "--applied", migration, "--schema", schemaPath]);
    }
  }
} finally {
  await prisma.$disconnect();
}

runPrisma(apiDir, ["migrate", "deploy", "--schema", schemaPath]);
console.log("prisma migration deploy ok");

function runPrisma(cwd, args) {
  const result = spawnSync(process.execPath, [prismaCliPath, ...args], {
    cwd,
    env: process.env,
    stdio: "inherit"
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
