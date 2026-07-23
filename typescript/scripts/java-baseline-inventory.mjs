import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const repoRoot = join(root, "..");
const javaRoot = join(repoRoot, "src", "main", "java");
const javaPackageRoot = join(javaRoot, "com", "enterprise", "iqk");
const javaConfigRoot = join(javaPackageRoot, "config");
const javaSecurityRoot = join(javaRoot, "com", "enterprise", "iqk", "security");
const javaMigrationRoot = join(repoRoot, "src", "main", "resources", "db", "migration");
const manifest = JSON.parse(readFileSync(join(root, "parity", "java-baseline.json"), "utf8"));
const prismaSchema = readFileSync(join(root, "prisma", "schema.prisma"), "utf8");
const prismaPhysicalTables = findPrismaPhysicalTables();
const prismaPhysicalModels = findPrismaPhysicalModels();
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
const configurationBySource = new Map(manifest.configurationMappings.map((mapping) => [mapping.source, mapping]));
const expectedConfigurationSemanticKeys = manifest.configurationMappings.flatMap((mapping) => mapping.typescriptFragments).sort();
const actualConfigurationSemanticKeys = manifest.configurationSemanticMappings.map((mapping) => mapping.typescriptKey).sort();
const actualConfigurationSources = findSources(javaRoot, (path) => readFileSync(path, "utf8").includes("@ConfigurationProperties("))
  .map((path) => relative(repoRoot, path))
  .sort();
const expectedCrossCuttingSources = manifest.crossCuttingMappings.map((mapping) => mapping.source).sort();
const actualCrossCuttingSources = [
  join(javaPackageRoot, "App.java"),
  ...findSources(javaConfigRoot, (path) => !relative(javaConfigRoot, path).startsWith("properties/") && basename(path) !== "SecurityConfiguration.java"),
  join(javaPackageRoot, "constants", "SystemConstants.java"),
  join(javaPackageRoot, "controller", "GlobalExceptionHandler.java"),
  ...findSources(join(javaPackageRoot, "tools"), () => true),
  ...findSources(join(javaPackageRoot, "util"), () => true),
  ...findSources(join(javaPackageRoot, "utils"), () => true)
].map((path) => relative(repoRoot, path)).sort();
const expectedSecuritySources = manifest.securityMappings.map((mapping) => mapping.source).sort();
const actualSecuritySources = findSources(javaSecurityRoot, () => true)
  .map((path) => relative(repoRoot, path))
  .sort();
const allJavaSources = findSources(javaRoot, (path) => path.endsWith(".java"))
  .map((path) => relative(repoRoot, path))
  .sort();
const explicitlyMappedJavaSources = new Set([
  ...manifest.controllers.map((mapping) => mapping.source),
  ...manifest.dtoMappings.map((mapping) => mapping.source),
  ...manifest.serviceMappings.map((mapping) => mapping.source),
  ...manifest.configurationMappings.map((mapping) => mapping.source),
  ...manifest.crossCuttingMappings.map((mapping) => mapping.source),
  ...manifest.securityMappings.map((mapping) => mapping.source),
  ...manifest.persistenceMappings.map((mapping) => mapping.source),
  manifest.securityWiring.source
]);
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
const javaEnumTypes = new Set(findSources(javaRoot, (path) => path.endsWith(".java"))
  .flatMap((path) => [...readFileSync(path, "utf8").matchAll(/\benum\s+([A-Za-z][A-Za-z0-9_]*)\b/g)].map((match) => match[1])));
let persistenceEntityCount = 0;
let persistenceFieldCount = 0;
let persistenceFieldExclusionCount = 0;
let configurationFragmentCount = 0;
let configurationSemanticCount = 0;
let configurationSameCount = 0;
let configurationRepresentationCount = 0;
let configurationDifferenceCount = 0;
let crossCuttingFragmentCount = 0;
let responsibilityGroupSourceCount = 0;
let responsibilityGroupAnchorCount = 0;
let securityFragmentCount = 0;
let fieldTypeFamilyCount = 0;
let fieldIsoRepresentationCount = 0;
let nestedTypeFieldCount = 0;
let nestedTypeSameCount = 0;
let nestedTypeDifferenceCount = 0;
let primitiveRequiredFieldCount = 0;
const javaMigrationTableColumns = new Map();
const javaMigrationSchema = findJavaMigrationSchema();

assertSameSet("Java controller baseline", expectedControllers, actualControllers);
assertSameSet("Java DTO baseline", expectedDtos, actualDtos);
assertSameSet("Java mapper baseline", expectedMappers, actualMappers);
assertSameSet("Java migration baseline", expectedMigrations, actualMigrations);
assertSameSet("Java configuration-properties baseline", expectedConfigurationSources, actualConfigurationSources);
assertSameSet("Java configuration semantic-key baseline", expectedConfigurationSemanticKeys, actualConfigurationSemanticKeys);
if (new Set(actualConfigurationSemanticKeys).size !== actualConfigurationSemanticKeys.length) {
  fail("Java configuration semantic-key baseline contains duplicate TypeScript keys");
}
assertSameSet("Java cross-cutting-source baseline", expectedCrossCuttingSources, actualCrossCuttingSources);
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

for (const mapping of manifest.configurationSemanticMappings) {
  const configuration = configurationBySource.get(mapping.source);
  if (!configuration) {
    fail(`${mapping.source} configuration semantic mapping has no declared configuration source`);
  }
  const javaSource = readFileSync(join(repoRoot, mapping.source), "utf8");
  const typescriptSource = readFileSync(join(root, configuration.typescriptSource), "utf8");
  assertIncludes(javaSource, mapping.javaFragment, `${mapping.source} Java configuration default`);
  assertIncludes(
    findEnvironmentEntry(typescriptSource, mapping.typescriptKey),
    `.default(${mapping.typescriptDefault})`,
    `${mapping.source} TypeScript configuration default`
  );
  if (!new Set(["same", "representation", "intentional_difference"]).has(mapping.relationship)) {
    fail(`${mapping.source} configuration semantic mapping has an invalid relationship: ${mapping.relationship}`);
  }
  if (mapping.relationship !== "same" && !mapping.note?.trim()) {
    fail(`${mapping.source} ${mapping.typescriptKey} configuration difference requires a note`);
  }
  configurationSemanticCount += 1;
  if (mapping.relationship === "same") {
    configurationSameCount += 1;
  } else if (mapping.relationship === "representation") {
    configurationRepresentationCount += 1;
  } else {
    configurationDifferenceCount += 1;
  }
}

for (const crossCutting of manifest.crossCuttingMappings) {
  const javaSource = readFileSync(join(repoRoot, crossCutting.source), "utf8");
  const typescriptSource = readFileSync(join(root, crossCutting.typescriptSource), "utf8");
  assertIncludes(javaSource, basename(crossCutting.source, ".java"), `${crossCutting.source} Java cross-cutting source`);
  for (const fragment of crossCutting.typescriptFragments) {
    assertIncludes(typescriptSource, fragment, `${crossCutting.source} TypeScript cross-cutting mapping`);
    crossCuttingFragmentCount += 1;
  }
}

for (const group of manifest.responsibilityGroupMappings) {
  const javaDirectory = join(repoRoot, group.javaDirectory);
  if (!existsSync(javaDirectory)) {
    fail(`${group.javaDirectory} Java responsibility directory is missing`);
  }
  const groupSources = findSources(javaDirectory, (path) => path.endsWith(".java"));
  if (groupSources.length === 0) {
    fail(`${group.javaDirectory} Java responsibility directory has no sources`);
  }
  responsibilityGroupSourceCount += groupSources.length;
  for (const source of groupSources) {
    explicitlyMappedJavaSources.add(relative(repoRoot, source));
  }
  for (const anchor of group.typescriptAnchors) {
    const typescriptSource = readFileSync(join(root, anchor.source), "utf8");
    for (const fragment of anchor.fragments) {
      assertIncludes(typescriptSource, fragment, `${group.javaDirectory} TypeScript responsibility-group mapping`);
      responsibilityGroupAnchorCount += 1;
    }
  }
}

assertSameSet("Java production-source responsibility baseline", allJavaSources, [...explicitlyMappedJavaSources].sort());

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

let migrationSchemaColumnCount = 0;
let migrationSchemaDefaultCount = 0;
let migrationSchemaConstraintCount = 0;
for (const [table, javaTable] of javaMigrationSchema) {
  const prismaModel = prismaPhysicalModels.get(table);
  if (!prismaModel) {
    fail(`Java migration table ${table} is missing from Prisma physical models`);
  }
  if (!sameSequence(javaTable.primaryKey, prismaModel.primaryKey)) {
    fail(`Java migration table ${table} primary key does not match Prisma: ${javaTable.primaryKey.join(", ")}`);
  }
  for (const [column, javaColumn] of javaTable.columns) {
    const prismaColumn = prismaModel.columns.get(column);
    if (!prismaColumn) {
      fail(`Java migration column ${table}.${column} is missing from Prisma physical models`);
    }
    if (javaColumn.sqlType !== prismaColumn.sqlType) {
      fail(`Java migration column ${table}.${column} type mismatch: ${javaColumn.sqlType} vs ${prismaColumn.sqlType}`);
    }
    if (javaColumn.nullable !== prismaColumn.nullable) {
      fail(`Java migration column ${table}.${column} nullability mismatch`);
    }
    if (javaColumn.defaultValue !== undefined && javaColumn.defaultValue !== prismaColumn.defaultValue) {
      fail(`Java migration column ${table}.${column} default mismatch: ${javaColumn.defaultValue} vs ${prismaColumn.defaultValue ?? "none"}`);
    }
    migrationSchemaColumnCount += 1;
    if (javaColumn.defaultValue !== undefined) {
      migrationSchemaDefaultCount += 1;
    }
  }
  for (const constraint of javaTable.constraints.filter((item) => item.named)) {
    const prismaConstraint = prismaModel.constraints.find((item) => item.name === constraint.name);
    if (!prismaConstraint || prismaConstraint.kind !== constraint.kind || !sameSequence(prismaConstraint.columns, constraint.columns)) {
      fail(`Java migration ${constraint.kind} ${constraint.name} on ${table} is missing or differs in Prisma`);
    }
    migrationSchemaConstraintCount += 1;
  }
}

for (const mapping of manifest.fieldMappings) {
  if (!knownDtoSources.has(mapping.source)) {
    fail(`${mapping.source} field mapping is not a declared Java DTO mapping`);
  }
  const javaSource = readFileSync(join(repoRoot, mapping.source), "utf8");
  const mappedJavaFields = [
    ...mapping.sameFields,
    ...(mapping.transforms ?? []).map((transform) => transform.java)
  ];
  if (new Set(mappedJavaFields).size !== mappedJavaFields.length) {
    fail(`${mapping.source} field mapping contains duplicate Java fields`);
  }
  assertSameSet(`${mapping.source} Java DTO field mapping`, findJavaInstanceFields(javaSource).sort(), [...mappedJavaFields].sort());
  const typescriptSource = readFileSync(join(root, mapping.typescriptSource), "utf8");
  if (!mapping.typescriptType?.trim()) {
    fail(`${mapping.source} field mapping is missing its TypeScript DTO type`);
  }
  const typescriptProperties = findTypescriptInterfaceProperties(typescriptSource, mapping.typescriptType);
  const typescriptFields = new Map([...typescriptProperties].map(([field, property]) => [field, property.type]));
  const nestedTypeMappings = new Map();
  for (const nestedMapping of mapping.nestedTypeMappings ?? []) {
    if (!nestedMapping.note?.trim() || nestedMapping.relationship !== "intentional_difference") {
      fail(`${mapping.source} nested type mapping requires an intentional-difference relationship and explanatory note`);
    }
    const key = `${nestedMapping.java}:${nestedMapping.typescript}`;
    if (nestedTypeMappings.has(key)) {
      fail(`${mapping.source} has a duplicate nested type mapping for ${key}`);
    }
    nestedTypeMappings.set(key, nestedMapping);
  }
  const usedNestedTypeMappings = new Set();
  for (const field of mapping.sameFields) {
    assertFieldTypeFamily(javaSource, typescriptFields, field, field, mapping);
    assertPrimitiveFieldRequired(javaSource, typescriptProperties, field, field, mapping);
    assertNestedTypeFamily(javaSource, typescriptFields, field, field, mapping, nestedTypeMappings, usedNestedTypeMappings);
  }
  for (const transform of mapping.transforms ?? []) {
    if (!transform.note?.trim() || transform.java === transform.typescript) {
      fail(`${mapping.source} field transform requires a renamed field and an explanatory note`);
    }
    assertFieldTypeFamily(javaSource, typescriptFields, transform.java, transform.typescript, mapping);
    assertPrimitiveFieldRequired(javaSource, typescriptProperties, transform.java, transform.typescript, mapping);
    assertNestedTypeFamily(javaSource, typescriptFields, transform.java, transform.typescript, mapping, nestedTypeMappings, usedNestedTypeMappings);
  }
  for (const key of nestedTypeMappings.keys()) {
    if (!usedNestedTypeMappings.has(key)) {
      fail(`${mapping.source} nested type mapping is stale or does not describe a type difference: ${key}`);
    }
  }
}

console.log(
  `java baseline inventory ok: ${allJavaSources.length}/${allJavaSources.length} Java production sources accounted for (${manifest.responsibilityGroupMappings.length} responsibility groups covering ${responsibilityGroupSourceCount} grouped sources and ${responsibilityGroupAnchorCount} group anchors), ${manifest.controllers.length} controllers, ${routeCount} route declarations, ${manifest.dtoMappings.length} DTOs, ${manifest.serviceMappings.length} core services, ${manifest.securityMappings.length} security sources and ${securityFragmentCount} security anchors, ${manifest.configurationMappings.length} configuration-property classes and ${configurationFragmentCount} key configuration anchors, ${configurationSemanticCount} configuration defaults (${configurationSameCount} same, ${configurationRepresentationCount} representation mappings, ${configurationDifferenceCount} documented differences), ${manifest.crossCuttingMappings.length} cross-cutting Java sources and ${crossCuttingFragmentCount} responsibility anchors, ${manifest.persistenceMappings.length} mapper/model pairs, ${persistenceEntityCount} Java entities and ${persistenceFieldCount} persistence fields, ${manifest.migrationMappings.length} migrations covering ${migrationTableCount} physical tables and ${migrationColumnCount} columns, ${migrationSchemaColumnCount} final schema columns with ${migrationSchemaDefaultCount} explicit defaults and ${migrationSchemaConstraintCount} named unique/index constraints, and ${fieldCount} key DTO fields map to TypeScript with ${fieldTypeFamilyCount} verified type families, ${nestedTypeFieldCount} verified collection/key-value shapes (${nestedTypeSameCount} same, ${nestedTypeDifferenceCount} documented differences), and ${primitiveRequiredFieldCount} required non-null primitive fields (${fieldIsoRepresentationCount} documented ISO-8601 representations; ${persistenceFieldExclusionCount} custom mapper field exclusion); static mapping only, not Java runtime parity`
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

function findEnvironmentEntry(source, key) {
  const marker = `  ${key}:`;
  const start = source.indexOf(marker);
  if (start < 0) {
    fail(`TypeScript environment key is missing: ${key}`);
  }
  const remaining = source.slice(start + marker.length);
  const nextEntry = remaining.search(/\n  [A-Z][A-Z0-9_]*:/);
  return source.slice(start, nextEntry < 0 ? source.length : start + marker.length + nextEntry);
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

function findJavaMigrationSchema() {
  const tables = new Map();
  for (const migration of manifest.migrationMappings) {
    const source = readFileSync(join(repoRoot, migration.source), "utf8");
    for (const rawStatement of source.split(";")) {
      const statement = rawStatement.replace(/^\s*--[^\n]*\n/gm, "").trim();
      if (!statement) {
        continue;
      }
      if (/^CREATE\s+TABLE\b/i.test(statement)) {
        addJavaCreateTable(statement, tables);
      } else if (/^ALTER\s+TABLE\b/i.test(statement)) {
        applyJavaAlterTable(statement, tables);
      } else if (/^CREATE\s+(?:UNIQUE\s+)?INDEX\b/i.test(statement)) {
        addJavaIndex(statement, tables);
      } else if (/^DROP\s+INDEX\b/i.test(statement)) {
        dropJavaIndex(statement, tables);
      }
    }
  }
  return tables;
}

function addJavaCreateTable(statement, tables) {
  const match = statement.match(/^CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s*\(([\s\S]*)\)$/i);
  if (!match) {
    fail(`cannot parse Java CREATE TABLE statement: ${statement.slice(0, 120)}`);
  }
  const [, name, body] = match;
  const table = { columns: new Map(), primaryKey: [], constraints: [] };
  tables.set(name, table);
  for (const rawLine of body.split("\n")) {
    const definition = rawLine.trim().replace(/,$/, "");
    if (!definition) {
      continue;
    }
    if (/^(PRIMARY|UNIQUE|INDEX|KEY|CONSTRAINT|FOREIGN|CHECK)\b/i.test(definition)) {
      addJavaTableConstraint(definition, table);
      continue;
    }
    addJavaColumn(definition, table);
  }
}

function applyJavaAlterTable(statement, tables) {
  const match = statement.match(/^ALTER\s+TABLE\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s+([\s\S]*)$/i);
  if (!match) {
    fail(`cannot parse Java ALTER TABLE statement: ${statement.slice(0, 120)}`);
  }
  const [, tableName, operations] = match;
  const table = tables.get(tableName);
  if (!table) {
    fail(`Java ALTER TABLE references unknown table: ${tableName}`);
  }
  for (const operation of operations.split(/,\s*(?=(?:ADD|DROP)\s)/i)) {
    const normalized = operation.trim();
    const addColumn = normalized.match(/^ADD\s+COLUMN\s+([\s\S]+)$/i);
    if (addColumn) {
      addJavaColumn(addColumn[1].trim(), table);
      continue;
    }
    const addUnique = normalized.match(/^ADD\s+UNIQUE\s+(?:KEY|INDEX)\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s*\(([^)]+)\)$/i);
    if (addUnique) {
      table.constraints.push({ name: addUnique[1], kind: "unique", columns: parsePhysicalColumns(addUnique[2]), named: true });
      continue;
    }
    const dropIndex = normalized.match(/^DROP\s+INDEX\s+`?([A-Za-z][A-Za-z0-9_]*)`?$/i);
    if (dropIndex) {
      table.constraints = table.constraints.filter((item) => item.name !== dropIndex[1]);
      continue;
    }
    fail(`cannot parse Java ALTER TABLE operation: ${normalized}`);
  }
}

function addJavaIndex(statement, tables) {
  const match = statement.match(/^CREATE\s+(UNIQUE\s+)?INDEX\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s+ON\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s*\(([^)]+)\)$/i);
  if (!match) {
    fail(`cannot parse Java CREATE INDEX statement: ${statement.slice(0, 120)}`);
  }
  const [, unique, name, tableName, columns] = match;
  const table = tables.get(tableName);
  if (!table) {
    fail(`Java CREATE INDEX references unknown table: ${tableName}`);
  }
  table.constraints.push({ name, kind: unique ? "unique" : "index", columns: parsePhysicalColumns(columns), named: true });
}

function dropJavaIndex(statement, tables) {
  const match = statement.match(/^DROP\s+INDEX\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s+ON\s+`?([A-Za-z][A-Za-z0-9_]*)`?$/i);
  if (!match) {
    fail(`cannot parse Java DROP INDEX statement: ${statement.slice(0, 120)}`);
  }
  const [, name, tableName] = match;
  const table = tables.get(tableName);
  if (!table) {
    fail(`Java DROP INDEX references unknown table: ${tableName}`);
  }
  table.constraints = table.constraints.filter((item) => item.name !== name);
}

function addJavaTableConstraint(definition, table) {
  const primary = definition.match(/^PRIMARY\s+KEY\s*\(([^)]+)\)$/i);
  if (primary) {
    table.primaryKey = parsePhysicalColumns(primary[1]);
    return;
  }
  const named = definition.match(/^(UNIQUE\s+KEY|UNIQUE\s+INDEX|INDEX|KEY)\s+`?([A-Za-z][A-Za-z0-9_]*)`?\s*\(([^)]+)\)$/i);
  if (named) {
    table.constraints.push({
      name: named[2],
      kind: /^UNIQUE/i.test(named[1]) ? "unique" : "index",
      columns: parsePhysicalColumns(named[3]),
      named: true
    });
  }
}

function addJavaColumn(definition, table) {
  const match = definition.match(/^`?([A-Za-z][A-Za-z0-9_]*)`?\s+([A-Za-z]+(?:\s*\([^)]*\))?)([\s\S]*)$/i);
  if (!match) {
    fail(`cannot parse Java column definition: ${definition}`);
  }
  const [, name, rawType, attributes] = match;
  const primaryKey = /\bPRIMARY\s+KEY\b/i.test(attributes);
  table.columns.set(name, {
    sqlType: normalizeSqlType(rawType),
    nullable: !primaryKey && !/\bNOT\s+NULL\b/i.test(attributes),
    defaultValue: parseDefaultValue(attributes, rawType)
  });
  if (primaryKey) {
    table.primaryKey = [name];
  }
  if (/\bUNIQUE\b/i.test(attributes)) {
    table.constraints.push({ name, kind: "unique", columns: [name], named: false });
  }
}

function findPrismaPhysicalModels() {
  const models = new Map();
  for (const match of prismaSchema.matchAll(/model\s+[A-Za-z][A-Za-z0-9_]*\s*\{([\s\S]*?)\n\}/g)) {
    const body = match[1];
    const tableMatch = body.match(/@@map\("([^"]+)"\)/);
    if (!tableMatch) {
      continue;
    }
    const model = { columns: new Map(), primaryKey: [], constraints: [] };
    for (const line of body.split("\n")) {
      const field = line.match(/^\s{2}([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z][A-Za-z0-9_]*)(\?)?([\s\S]*)$/);
      if (!field) {
        continue;
      }
      const [, name, type, optional, attributes] = field;
      const physicalName = attributes.match(/@map\("([^"]+)"\)/)?.[1] ?? name;
      model.columns.set(physicalName, {
        fieldName: name,
        sqlType: prismaSqlType(type, attributes),
        nullable: optional === "?",
        defaultValue: parsePrismaDefault(attributes, type)
      });
      if (/@id\b/.test(attributes)) {
        model.primaryKey = [physicalName];
      }
      if (/@unique\b/.test(attributes)) {
        const uniqueName = attributes.match(/@unique\(map:\s*"([^"]+)"\)/)?.[1];
        model.constraints.push({ name: uniqueName, kind: "unique", columns: [physicalName] });
      }
    }
    for (const constraint of body.matchAll(/@@(unique|index)\(\[([^\]]+)\](?:,\s*map:\s*"([^"]+)")?\)/g)) {
      const [, kind, fields, name] = constraint;
      const physicalColumns = fields.split(",").map((field) => field.trim().split(/\s+/)[0]).map((field) => {
        for (const [column, value] of model.columns) {
          if (value.fieldName === field) {
            return column;
          }
        }
        return field;
      });
      model.constraints.push({ name, kind, columns: physicalColumns });
    }
    models.set(tableMatch[1], model);
  }
  return models;
}

function prismaSqlType(type, attributes) {
  const databaseType = attributes.match(/@db\.([A-Za-z]+)(?:\(([^)]*)\))?/);
  if (databaseType) {
    return normalizeSqlType(`${databaseType[1]}${databaseType[2] === undefined ? "" : `(${databaseType[2]})`}`);
  }
  return new Map([
    ["BigInt", "BIGINT"],
    ["Int", "INT"],
    ["Boolean", "TINYINT(1)"],
    ["Float", "DOUBLE"],
    ["DateTime", "DATETIME"],
    ["Json", "JSON"]
  ]).get(type) ?? type.toUpperCase();
}

function parsePrismaDefault(attributes, type) {
  const value = attributes.match(/@default\(([^)]*)\)/)?.[1];
  if (!value || value === "autoincrement()") {
    return undefined;
  }
  return normalizeDefaultValue(value, type === "Boolean" ? "TINYINT(1)" : type);
}

function parseDefaultValue(attributes, rawType) {
  const value = attributes.match(/\bDEFAULT\s+('(?:[^']|'')*'|"(?:[^"]|"")*"|[^\s,]+)/i)?.[1];
  return value === undefined ? undefined : normalizeDefaultValue(value, rawType);
}

function normalizeDefaultValue(value, type) {
  const unquoted = value.trim().replace(/^['"]|['"]$/g, "");
  if (normalizeSqlType(type) === "TINYINT(1)") {
    if (unquoted === "1" || unquoted === "true") {
      return "true";
    }
    if (unquoted === "0" || unquoted === "false") {
      return "false";
    }
  }
  if (/^-?\d+(?:\.\d+)?$/.test(unquoted)) {
    return String(Number(unquoted));
  }
  return unquoted;
}

function normalizeSqlType(type) {
  return type.replace(/\s+/g, "").toUpperCase();
}

function parsePhysicalColumns(value) {
  return value.split(",").map((column) => column.trim().replace(/`/g, ""));
}

function sameSequence(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
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

function assertFieldTypeFamily(javaSource, typescriptFields, javaField, typescriptField, mapping) {
  const javaType = findJavaFieldType(javaSource, javaField, `${mapping.source} Java field`);
  const typescriptType = typescriptFields.get(typescriptField);
  if (!typescriptType) {
    fail(`${mapping.source} ${mapping.typescriptType} TypeScript field is missing: ${typescriptField}`);
  }
  const javaFamily = javaTypeFamily(javaType);
  const typescriptFamily = typescriptTypeFamily(typescriptType);
  if (javaFamily === "temporal" && typescriptFamily === "text") {
    if (!/ISO-8601/i.test(mapping.representation ?? "")) {
      fail(`${mapping.source} ${javaField} maps LocalDateTime to TypeScript text without an ISO-8601 representation note`);
    }
    fieldIsoRepresentationCount += 1;
  } else if (javaFamily !== typescriptFamily) {
    fail(`${mapping.source} ${javaField} type-family mismatch: Java ${javaType} (${javaFamily}) vs TypeScript ${typescriptType} (${typescriptFamily})`);
  }
  fieldTypeFamilyCount += 1;
}

function assertNestedTypeFamily(javaSource, typescriptFields, javaField, typescriptField, mapping, nestedTypeMappings, usedNestedTypeMappings) {
  const javaType = findJavaFieldType(javaSource, javaField, `${mapping.source} Java field`);
  const typescriptType = typescriptFields.get(typescriptField);
  const javaShape = javaTypeShape(javaType);
  const typescriptShape = typescriptTypeShape(typescriptType);
  if (!javaShape.nested && !typescriptShape.nested) {
    return;
  }
  nestedTypeFieldCount += 1;
  const key = `${javaField}:${typescriptField}`;
  if (sameTypeShape(javaShape, typescriptShape)) {
    nestedTypeSameCount += 1;
    return;
  }
  const documentedDifference = nestedTypeMappings.get(key);
  if (!documentedDifference) {
    fail(`${mapping.source} ${javaField} nested type mismatch: Java ${typeShapeLabel(javaShape)} vs TypeScript ${typeShapeLabel(typescriptShape)}`);
  }
  usedNestedTypeMappings.add(key);
  nestedTypeDifferenceCount += 1;
}

function assertPrimitiveFieldRequired(javaSource, typescriptProperties, javaField, typescriptField, mapping) {
  const javaType = findJavaFieldType(javaSource, javaField, `${mapping.source} Java field`);
  if (!/^(byte|short|int|long|float|double|boolean)$/.test(javaType)) {
    return;
  }
  const property = typescriptProperties.get(typescriptField);
  if (!property || property.optional || typeAllowsNull(property.type)) {
    fail(`${mapping.source} ${javaField} is a non-null Java primitive but TypeScript ${typescriptField} is optional or nullable`);
  }
  primitiveRequiredFieldCount += 1;
}

function findJavaFieldType(source, field, label) {
  const match = source.match(new RegExp(`^\\s*private\\s+(?!static\\b)([^;=]+?)\\s+${escapeRegex(field)}\\s*;\\s*$`, "m"));
  if (!match) {
    fail(`${label} is missing: ${field}`);
  }
  return match[1].trim();
}

function findTypescriptInterfaceProperties(source, typeName, seen = new Set()) {
  if (seen.has(typeName)) {
    fail(`TypeScript interface inheritance cycle: ${[...seen, typeName].join(" -> ")}`);
  }
  const declaration = new RegExp(`export\\s+interface\\s+${escapeRegex(typeName)}(?:\\s*<[^>{}]+>)?\\s*(?:extends\\s+([^\\{]+))?\\s*\\{`, "m").exec(source);
  if (!declaration) {
    fail(`TypeScript interface is missing: ${typeName}`);
  }
  const openBrace = declaration.index + declaration[0].lastIndexOf("{");
  const closeBrace = findMatchingBrace(source, openBrace);
  const properties = new Map();
  const parents = declaration[1]?.split(",").map((parent) => parent.trim().replace(/<.*>/, "")).filter(Boolean) ?? [];
  for (const parent of parents) {
    for (const [field, property] of findTypescriptInterfaceProperties(source, parent, new Set([...seen, typeName]))) {
      properties.set(field, property);
    }
  }
  const body = source.slice(openBrace + 1, closeBrace);
  for (const match of body.matchAll(/^\s*([A-Za-z][A-Za-z0-9_]*)(\?)?\s*:\s*([^;\n]+);/gm)) {
    properties.set(match[1], { optional: Boolean(match[2]), type: match[3].trim() });
  }
  return properties;
}

function findMatchingBrace(source, openBrace) {
  let depth = 0;
  for (let index = openBrace; index < source.length; index += 1) {
    if (source[index] === "{") {
      depth += 1;
    } else if (source[index] === "}" && --depth === 0) {
      return index;
    }
  }
  fail("TypeScript interface body is not closed");
}

function javaTypeFamily(type) {
  const normalized = type.replace(/\s+/g, "");
  if (/^(byte|short|int|long|float|double|Byte|Short|Integer|Long|Float|Double|BigDecimal|BigInteger)$/.test(normalized)) {
    return "number";
  }
  if (/^(boolean|Boolean)$/.test(normalized)) {
    return "boolean";
  }
  if (/^(LocalDate|LocalDateTime|OffsetDateTime|Instant|ZonedDateTime|Date|Timestamp)$/.test(normalized)) {
    return "temporal";
  }
  if (/^(List|Set|Collection|Iterable|Stream)<|\[\]$/.test(normalized)) {
    return "collection";
  }
  if (/^Map</.test(normalized)) {
    return "record";
  }
  if (normalized === "Object") {
    return "unknown";
  }
  if (normalized === "String" || normalized === "UUID" || javaEnumTypes.has(normalized)) {
    return "text";
  }
  return "structured";
}

function typescriptTypeFamily(type) {
  const normalized = type.replace(/\s+/g, " ").trim();
  const nonNullable = normalized.split("|").map((part) => part.trim()).filter((part) => part !== "null" && part !== "undefined");
  const primary = nonNullable.join(" | ");
  if (/^(Array|ReadonlyArray)</.test(primary) || /\[\]$/.test(primary)) {
    return "collection";
  }
  if (/^Record</.test(primary)) {
    return "record";
  }
  if (primary === "unknown" || primary === "any") {
    return "unknown";
  }
  if (primary === "number" || nonNullable.every((part) => /^-?\d+(\.\d+)?$/.test(part))) {
    return "number";
  }
  if (primary === "boolean" || nonNullable.every((part) => part === "true" || part === "false")) {
    return "boolean";
  }
  if (primary === "string" || nonNullable.every((part) => /^(["']).*\1$/.test(part))) {
    return "text";
  }
  return "structured";
}

function typeAllowsNull(type) {
  return splitTopLevel(type, "|").some((part) => part.trim() === "null" || part.trim() === "undefined");
}

function javaTypeShape(type) {
  const normalized = type.replace(/\s+/g, "");
  const collection = normalized.match(/^(?:List|Set|Collection|Iterable|Stream)<(.*)>$/);
  if (collection) {
    return { nested: true, family: "collection", element: javaTypeShape(collection[1]) };
  }
  const map = normalized.match(/^Map<(.*)>$/);
  if (map) {
    const [key, value] = splitTypeArguments(map[1]);
    if (!key || !value) {
      fail(`unsupported Java map type: ${type}`);
    }
    return { nested: true, family: "record", key: javaTypeShape(key), value: javaTypeShape(value) };
  }
  return { nested: false, family: javaTypeFamily(normalized) };
}

function typescriptTypeShape(type) {
  const normalized = removeNullableType(type);
  const collection = normalized.match(/^(?:Array|ReadonlyArray)<(.*)>$/);
  if (collection) {
    return { nested: true, family: "collection", element: typescriptTypeShape(collection[1]) };
  }
  if (normalized.endsWith("[]")) {
    return { nested: true, family: "collection", element: typescriptTypeShape(normalized.slice(0, -2)) };
  }
  const record = normalized.match(/^Record<(.*)>$/);
  if (record) {
    const [key, value] = splitTypeArguments(record[1]);
    if (!key || !value) {
      fail(`unsupported TypeScript record type: ${type}`);
    }
    return { nested: true, family: "record", key: typescriptTypeShape(key), value: typescriptTypeShape(value) };
  }
  return { nested: false, family: typescriptTypeFamily(normalized) };
}

function removeNullableType(type) {
  const parts = splitTopLevel(type, "|").map((part) => part.trim()).filter((part) => part !== "null" && part !== "undefined");
  return parts.join(" | ");
}

function splitTypeArguments(value) {
  return splitTopLevel(value, ",").map((part) => part.trim());
}

function splitTopLevel(value, separator) {
  const parts = [];
  let start = 0;
  let depth = 0;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === "<") {
      depth += 1;
    } else if (value[index] === ">") {
      depth -= 1;
    } else if (value[index] === separator && depth === 0) {
      parts.push(value.slice(start, index));
      start = index + 1;
    }
  }
  parts.push(value.slice(start));
  return parts;
}

function sameTypeShape(left, right) {
  if (left.family !== right.family) {
    return false;
  }
  if (left.family === "collection") {
    return sameTypeShape(left.element, right.element);
  }
  if (left.family === "record") {
    return sameTypeShape(left.key, right.key) && sameTypeShape(left.value, right.value);
  }
  return true;
}

function typeShapeLabel(shape) {
  if (shape.family === "collection") {
    return `collection<${typeShapeLabel(shape.element)}>`;
  }
  if (shape.family === "record") {
    return `record<${typeShapeLabel(shape.key)}, ${typeShapeLabel(shape.value)}>`;
  }
  return shape.family;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
