import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const repoRoot = join(root, "..");
const javaRoot = join(repoRoot, "src", "main", "java");
const javaMigrationRoot = join(repoRoot, "src", "main", "resources", "db", "migration");
const manifest = JSON.parse(readFileSync(join(root, "parity", "java-baseline.json"), "utf8"));
const typescriptSource = readSources(join(root, "apps", "api", "src")).join("\n");
const prismaSchema = readFileSync(join(root, "prisma", "schema.prisma"), "utf8");
const expectedControllers = manifest.controllers.map((controller) => controller.source).sort();
const actualControllers = findJavaControllers(javaRoot).map((path) => relative(repoRoot, path)).sort();
const expectedDtos = manifest.dtoMappings.map((dto) => dto.source).sort();
const actualDtos = findSources(javaRoot, (path) => {
  const file = basename(path);
  return file.endsWith("VO.java") || file === "PagedResult.java" || file === "Result.java";
}).map((path) => relative(repoRoot, path)).sort();
const expectedMappers = manifest.persistenceMappings.map((mapping) => mapping.source).sort();
const actualMappers = findSources(javaRoot, (path) => basename(path).endsWith("Mapper.java"))
  .map((path) => relative(repoRoot, path))
  .sort();
const expectedMigrations = manifest.migrationMappings.map((mapping) => mapping.source).sort();
const actualMigrations = findSources(javaMigrationRoot, (path) => path.endsWith(".sql"))
  .map((path) => relative(repoRoot, path))
  .sort();

assertSameSet("Java controller baseline", expectedControllers, actualControllers);
assertSameSet("Java DTO baseline", expectedDtos, actualDtos);
assertSameSet("Java mapper baseline", expectedMappers, actualMappers);
assertSameSet("Java migration baseline", expectedMigrations, actualMigrations);

let routeCount = 0;
for (const controller of manifest.controllers) {
  const javaPath = join(repoRoot, controller.source);
  if (!existsSync(javaPath)) {
    fail(`missing Java source: ${controller.source}`);
  }
  const javaSource = readFileSync(javaPath, "utf8");
  assertIncludes(javaSource, controller.javaBase, `${controller.source} baseline mapping`);
  if (controller.typescriptBase) {
    assertIncludes(typescriptSource, controller.typescriptBase, `${controller.source} TypeScript controller mapping`);
  }
  for (const route of controller.routes) {
    routeCount += 1;
    assertIncludes(javaSource, route.java, `${controller.source} Java route`);
    for (const fragment of route.typescript) {
      assertIncludes(typescriptSource, fragment, `${controller.source} TypeScript route`);
    }
  }
}

for (const dto of manifest.dtoMappings) {
  const javaPath = join(repoRoot, dto.source);
  const javaType = basename(dto.source, ".java");
  const typescriptPath = join(root, dto.typescriptSource);
  assertIncludes(readFileSync(javaPath, "utf8"), `class ${javaType}`, `${dto.source} Java DTO`);
  assertIncludes(readFileSync(typescriptPath, "utf8"), dto.typescriptFragment, `${dto.source} TypeScript DTO mapping`);
}

for (const service of manifest.serviceMappings) {
  const javaPath = join(repoRoot, service.source);
  const javaType = basename(service.source, ".java");
  const typescriptPath = join(root, service.typescriptSource);
  assertIncludes(readFileSync(javaPath, "utf8"), `class ${javaType}`, `${service.source} Java service`);
  assertIncludes(readFileSync(typescriptPath, "utf8"), service.typescriptFragment, `${service.source} TypeScript service mapping`);
}

for (const mapping of manifest.persistenceMappings) {
  const javaPath = join(repoRoot, mapping.source);
  const javaType = basename(mapping.source, ".java");
  assertIncludes(readFileSync(javaPath, "utf8"), `interface ${javaType}`, `${mapping.source} Java mapper`);
  assertIncludes(prismaSchema, `model ${mapping.typescriptModel} {`, `${mapping.source} Prisma model mapping`);
}

for (const migration of manifest.migrationMappings) {
  if (!existsSync(join(root, migration.typescriptSource))) {
    fail(`${migration.source} is missing TypeScript migration: ${migration.typescriptSource}`);
  }
}

console.log(
  `java baseline inventory ok: ${manifest.controllers.length} controllers, ${routeCount} route declarations, ${manifest.dtoMappings.length} DTOs, ${manifest.serviceMappings.length} core services, ${manifest.persistenceMappings.length} mapper/model pairs, and ${manifest.migrationMappings.length} migrations map to TypeScript; static mapping only, not Java runtime parity`
);

function findJavaControllers(dir) {
  return findSources(dir, (path) => path.endsWith("Controller.java"));
}

function findSources(dir, predicate) {
  const files = [];
  for (const entry of readdirSync(dir).sort()) {
    const path = join(dir, entry);
    const stats = statSync(path);
    if (stats.isDirectory()) {
      files.push(...findSources(path, predicate));
    } else if (predicate(path)) {
      files.push(path);
    }
  }
  return files;
}

function readSources(dir) {
  const files = [];
  for (const entry of readdirSync(dir).sort()) {
    const path = join(dir, entry);
    const stats = statSync(path);
    if (stats.isDirectory()) {
      files.push(...readSources(path));
    } else if (path.endsWith(".ts") && !path.endsWith(".spec.ts")) {
      files.push(readFileSync(path, "utf8"));
    }
  }
  return files;
}

function assertSameSet(label, expected, actual) {
  const missing = expected.filter((value) => !actual.includes(value));
  const unexpected = actual.filter((value) => !expected.includes(value));
  if (missing.length > 0 || unexpected.length > 0) {
    fail(`${label} changed; update parity/java-baseline.json. Missing: ${missing.join(", ") || "none"}. Unexpected: ${unexpected.join(", ") || "none"}`);
  }
}

function assertIncludes(source, fragment, label) {
  if (!source.includes(fragment)) {
    fail(`${label} is missing fragment: ${fragment}`);
  }
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
