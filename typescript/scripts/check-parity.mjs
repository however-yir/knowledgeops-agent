import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(root, "parity", "manifest.json"), "utf8"));

const missingFiles = manifest.requiredFiles.filter((file) => !existsSync(join(root, file)));
const source = readSources(join(root, "apps", "api", "src")).join("\n");
const missingRoutes = manifest.requiredRoutes.filter((route) => {
  return !route.tsFragments.every((fragment) => source.includes(fragment));
});

if (missingFiles.length > 0 || missingRoutes.length > 0) {
  for (const file of missingFiles) {
    console.error(`missing file: ${file}`);
  }
  for (const route of missingRoutes) {
    console.error(`missing route: ${route.label}`);
  }
  process.exit(1);
}

console.log(`parity ok: ${manifest.requiredFiles.length} files, ${manifest.requiredRoutes.length} routes`);

function readSources(dir) {
  const entries = readdirSync(dir).sort();
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry);
    const stats = statSync(path);
    if (stats.isDirectory()) {
      files.push(...readSources(path));
    } else if (path.endsWith(".ts") && !path.endsWith(".spec.ts")) {
      files.push(`// ${relative(root, path)}\n${readFileSync(path, "utf8")}`);
    }
  }
  return files;
}
