import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const repoRoot = join(root, "..");
const javaRoot = join(repoRoot, "src", "main", "java");
const javaSecurityRoot = join(javaRoot, "com", "enterprise", "iqk", "security");
const javaMigrationRoot = join(repoRoot, "src", "main", "resources", "db", "migration");
const manifest = JSON.parse(readFileSync(join(root, "parity", "java-baseline.json"), "utf8"));
const prismaSchema = readFileSync(join(root, "prisma", "schema.prisma"), "utf8");
const prismaPhysicalTables = findPrismaPhysicalTables();
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
const expectedConfigurationSources = manifest.configurationMappings.map((mapping) => mapping.source).sort();
const actualConfigurationSources = findSources(javaRoot, (path) => readFileSync(path, "utf8").includes("@ConfigurationProperties("))
  .map((path) => relative(repoRoot, path))
  .sort();
const expectedSecuritySources = manifest.securityMappings.map((mapping) => mapping.source).sort();
const actualSecuritySources = findSources(javaSecurityRoot, () => true)
  .map((path) => relative(repoRoot, path))
  .sort();
const javaSourcesByBasename = new Map();
for (const path of findSources(javaRoot, () => true)) {
  const name = basename(path);
  javaSourcesByBasename.set(name, [...(javaSourcesByBasename.get(name) ?? []), path]);
}
const expectedFieldDtos = manifest.dtoMappings.map((dto) => dto.source).sort();
const actualFieldDtos = manifest.fieldMappings.map((mapping) => mapping.source).sort();
const knownDtoSources = new Set(manifest.dtoMappings.map((dto) => dto.source));
const fieldCount = manifest.fieldMappings.reduce((count, mapping) => {
  return count + mapping.sameFields.length + (mapping.transforms?.length ?? 0);
}, 0);
let persistenceEntityCount = 0;
let persistenceFieldCount = 0;
let persistenceFieldExclusionCount = 0;
let configurationFragmentCount = 0;
let securityFragmentCount = 0;
const javaMigrationTableColumns = new Map();

assertSameSet("Java controller baseline", expectedControllers, actualControllers);
assertSameSet("Java DTO baseline", expectedDtos, actualDtos);
assertSameSet("Java mapper baseline", expectedMappers, actualMappers);
assertSameSet("Java migration baseline", expectedMigrations, actualMigrations);
assertSameSet("Java configuration-properties baseline", expectedConfigurationSources, actualConfigurationSources);
assertSameSet("Java security-source baseline", expectedSecuritySources, actualSecuritySources);
assertSameSet("Java DTO field baseline", expectedFieldDtos, actualFieldDtos);

let routeCount = 0;
for (const controller of manifest.controllers) {
  const javaPath = join(repoRoot, controller.source);
  if (!existsSync(javaPath)) {
    fail(`missing Java source: ${controller.source}`);
  }
  const javaSource = readFileSync(javaPath, "utf8");
  const typescriptPath = join(root, controller.typescriptSource ?? "");
  if (!controller.typescriptSource || !existsSync(typescriptPath)) {
    fail(`${controller.source} is missing its TypeScript controller source mapping`);
  }
  const controllerTypescriptSource = readFileSync(typescriptPath, "utf8");
  assertIncludes(javaSource, controller.javaBase, `${controller.source} baseline mapping`);
  if (controller.typescriptBase) {
    assertIncludes(controllerTypescriptSource, controller.typescriptBase, `${controller.source} TypeScript controller mapping`);
  }
  for (const route of controller.routes) {
    routeCount += 1;
    assertIncludes(javaSource, route.java, `${controller.source} Java route`);
    const routeTypescriptPath = join(root, route.typescriptSource ?? controller.typescriptSource);
    if (!existsSync(routeTypescriptPath)) {
      fail(`${controller.source} TypeScript route source is missing: ${route.typescriptSource ?? controller.typescriptSource}`);
    }
    const routeTypescriptSource = route.typescriptSource
      ? readFileSync(routeTypescriptPath, "utf8")
      : controllerTypescriptSource;
    for (const fragment of route.typescript) {
      assertIncludes(routeTypescriptSource, fragment, `${controller.source} TypeScript route`);
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

for (const configuration of manifest.configurationMappings) {
  const javaSource = readFileSync(join(repoRoot, configuration.source), "utf8");
  const typescriptSource = readFileSync(join(root, configuration.typescriptSource), "utf8");
  assertIncludes(
    javaSource,
    `@ConfigurationProperties(prefix = "${configuration.javaPrefix}")`,
    `${configuration.source} Java configuration prefix`
  );
  for (const fragment of configuration.typescriptFragments) {
    assertIncludes(typescriptSource, fragment, `${configuration.source} TypeScript configuration mapping`);
    configurationFragmentCount += 1;
  }
}

for (const security of manifest.securityMappings) {
  const javaSource = readFileSync(join(repoRoot, security.source), "utf8");
  const typescriptSource = readFileSync(join(root, security.typescriptSource), "utf8");
  assertIncludes(javaSource, basename(security.source, ".java"), `${security.source} Java security source`);
  for (const fragment of security.typescriptFragments) {
    assertIncludes(typescriptSource, fragment, `${security.source} TypeScript security mapping`);
    securityFragmentCount += 1;
  }
}

const securityWiringJavaSource = readFileSync(join(repoRoot, manifest.securityWiring.source), "utf8");
const securityWiringTypescriptSource = readFileSync(join(root, manifest.securityWiring.typescriptSource), "utf8");
assertIncludes(securityWiringJavaSource, "class SecurityConfiguration", `${manifest.securityWiring.source} Java security wiring`);
for (const fragment of manifest.securityWiring.typescriptFragments) {
  assertIncludes(securityWiringTypescriptSource, fragment, `${manifest.securityWiring.source} TypeScript security wiring`);
  securityFragmentCount += 1;
}

for (const mapping of manifest.persistenceMappings) {
  const javaPath = join(repoRoot, mapping.source);
  const javaType = basename(mapping.source, ".java");
  const mapperSource = readFileSync(javaPath, "utf8");
  assertIncludes(mapperSource, `interface ${javaType}`, `${mapping.source} Java mapper`);
  assertIncludes(prismaSchema, `model ${mapping.typescriptModel} {`, `${mapping.source} Prisma model mapping`);
  const entityType = mapperSource.match(/BaseMapper<([A-Za-z][A-Za-z0-9_]*)>/)?.[1];
  if (!entityType) {
    if (!mapping.fieldMappingExcluded?.trim()) {
      fail(`${mapping.source} has no BaseMapper entity and must declare a field-mapping exclusion`);
    }
    persistenceFieldExclusionCount += 1;
    continue;
  }
  if (mapping.fieldMappingExcluded) {
    fail(`${mapping.source} has a BaseMapper entity and must not exclude field mapping`);
  }
  const entityPaths = javaSourcesByBasename.get(`${entityType}.java`) ?? [];
  if (entityPaths.length !== 1) {
    fail(`${mapping.source} BaseMapper entity ${entityType} must resolve to exactly one Java source; found ${entityPaths.length}`);
  }
  const entitySource = readFileSync(entityPaths[0], "utf8");
  const entityFields = findJavaInstanceFields(entitySource);
  if (entityFields.length === 0) {
    fail(`${mapping.source} BaseMapper entity ${entityType} has no Java instance fields`);
  }
  const prismaFields = findPrismaModelFields(mapping.typescriptModel);
  for (const field of entityFields) {
    if (!prismaFields.has(field)) {
      fail(`${mapping.source} Java entity field ${field} is missing from Prisma model ${mapping.typescriptModel}`);
    }
  }
  persistenceEntityCount += 1;
  persistenceFieldCount += entityFields.length;
}

for (const migration of manifest.migrationMappings) {
  if (!existsSync(join(root, migration.typescriptSource))) {
    fail(`${migration.source} is missing TypeScript migration: ${migration.typescriptSource}`);
  }
  for (const [table, fields] of findJavaMigrationTableColumns(readFileSync(join(repoRoot, migration.source), "utf8"))) {
    const knownFields = javaMigrationTableColumns.get(table) ?? new Set();
    for (const field of fields) {
      knownFields.add(field);
    }
    javaMigrationTableColumns.set(table, knownFields);
  }
}

let migrationTableCount = 0;
let migrationColumnCount = 0;
for (const [table, fields] of javaMigrationTableColumns) {
  const prismaFields = prismaPhysicalTables.get(table);
  if (!prismaFields) {
    fail(`Java migration table ${table} is missing from Prisma physical mappings`);
  }
  for (const field of fields) {
    if (!prismaFields.has(field)) {
      fail(`Java migration column ${table}.${field} is missing from Prisma physical mappings`);
    }
  }
  migrationTableCount += 1;
  migrationColumnCount += fields.size;
}

for (const mapping of manifest.fieldMappings) {
  if (!knownDtoSources.has(mapping.source)) {
    fail(`${mapping.source} field mapping is not a declared Java DTO mapping`);
  }
  const javaSource = readFileSync(join(repoRoot, mapping.source), "utf8");
  const typescriptSource = readFileSync(join(root, mapping.typescriptSource), "utf8");
  for (const field of mapping.sameFields) {
    assertJavaField(javaSource, field, `${mapping.source} Java field`);
    assertTypescriptField(typescriptSource, field, `${mapping.source} TypeScript field`);
  }
  for (const transform of mapping.transforms ?? []) {
    if (!transform.note?.trim() || transform.java === transform.typescript) {
      fail(`${mapping.source} field transform requires a renamed field and an explanatory note`);
    }
    assertJavaField(javaSource, transform.java, `${mapping.source} Java transformed field`);
    assertTypescriptField(typescriptSource, transform.typescript, `${mapping.source} TypeScript transformed field`);
  }
}

console.log(
  `java baseline inventory ok: ${manifest.controllers.length} controllers, ${routeCount} route declarations, ${manifest.dtoMappings.length} DTOs, ${manifest.serviceMappings.length} core services, ${manifest.securityMappings.length} security sources and ${securityFragmentCount} security anchors, ${manifest.configurationMappings.length} configuration-property classes and ${configurationFragmentCount} key configuration anchors, ${manifest.persistenceMappings.length} mapper/model pairs, ${persistenceEntityCount} Java entities and ${persistenceFieldCount} persistence fields, ${manifest.migrationMappings.length} migrations covering ${migrationTableCount} physical tables and ${migrationColumnCount} columns, and ${fieldCount} key DTO fields map to TypeScript (${persistenceFieldExclusionCount} custom mapper field exclusion); static mapping only, not Java runtime parity`
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

function assertJavaField(source, field, label) {
  if (!new RegExp(`\\b${escapeRegex(field)}\\s*;`).test(source)) {
    fail(`${label} is missing: ${field}`);
  }
}

function findJavaInstanceFields(source) {
  return [...source.matchAll(/^\s*private\s+(?!static\b)[^;=]+\s+([A-Za-z][A-Za-z0-9_]*)\s*;/gm)].map((match) => match[1]);
}

function findPrismaModelFields(model) {
  const match = prismaSchema.match(new RegExp(`model\\s+${escapeRegex(model)}\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!match) {
    fail(`missing Prisma model body: ${model}`);
  }
  return new Set([...match[1].matchAll(/^\s{2}([A-Za-z][A-Za-z0-9_]*)\s/gm)].map((field) => field[1]));
}

function findPrismaPhysicalTables() {
  const tables = new Map();
  for (const match of prismaSchema.matchAll(/model\s+[A-Za-z][A-Za-z0-9_]*\s*\{([\s\S]*?)\n\s*@@map\("([^"]+)"\)\n\}/g)) {
    const [, body, table] = match;
    const fields = new Set();
    for (const line of body.split("\n")) {
      const field = line.match(/^\s{2}([A-Za-z][A-Za-z0-9_]*)\s+\S+(.*)$/);
      if (field) {
        fields.add(field[2].match(/@map\("([^"]+)"\)/)?.[1] ?? field[1]);
      }
    }
    tables.set(table, fields);
  }
  return tables;
}

function findJavaMigrationTableColumns(source) {
  const tables = new Map();
  const ignoredDefinitions = new Set(["PRIMARY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN", "CHECK"]);
  for (const match of source.matchAll(/CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+`?([a-z][a-z0-9_]*)`?\s*\(([\s\S]*?)\n\);/gi)) {
    const [, table, body] = match;
    const fields = new Set();
    for (const line of body.split("\n")) {
      const field = line.trim().match(/^`?([a-z][a-z0-9_]*)`?\s+[A-Z]/i)?.[1];
      if (field && !ignoredDefinitions.has(field.toUpperCase())) {
        fields.add(field);
      }
    }
    tables.set(table, fields);
  }
  for (const match of source.matchAll(/ALTER\s+TABLE\s+`?([a-z][a-z0-9_]*)`?\s+ADD\s+COLUMN\s+`?([a-z][a-z0-9_]*)`?/gi)) {
    const [, table, field] = match;
    const fields = tables.get(table) ?? new Set();
    fields.add(field);
    tables.set(table, fields);
  }
  return tables;
}

function assertTypescriptField(source, field, label) {
  if (!new RegExp(`\\b${escapeRegex(field)}\\??\\s*:`).test(source)) {
    fail(`${label} is missing: ${field}`);
  }
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
