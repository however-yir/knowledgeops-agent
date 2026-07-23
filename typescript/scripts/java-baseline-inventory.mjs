import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const repoRoot = join(root, "..");
const javaRoot = join(repoRoot, "src", "main", "java");
const manifest = JSON.parse(readFileSync(join(root, "parity", "java-baseline.json"), "utf8"));
const typescriptSource = readSources(join(root, "apps", "api", "src")).join("\n");
const expectedControllers = manifest.controllers.map((controller) => controller.source).sort();
const actualControllers = findJavaControllers(javaRoot).map((path) => relative(repoRoot, path)).sort();

assertSameSet("Java controller baseline", expectedControllers, actualControllers);

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

console.log(
  `java baseline inventory ok: ${manifest.controllers.length} controllers and ${routeCount} route declarations map to TypeScript; static mapping only, not Java runtime parity`
);

function findJavaControllers(dir) {
  const files = [];
  for (const entry of readdirSync(dir).sort()) {
    const path = join(dir, entry);
    const stats = statSync(path);
    if (stats.isDirectory()) {
      files.push(...findJavaControllers(path));
    } else if (entry.endsWith("Controller.java")) {
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
