import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const cases = JSON.parse(readFileSync(join(root, "parity", "contract-cases.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(root, "parity", "manifest.json"), "utf8"));
const labels = new Set(manifest.requiredRoutes.map((route) => route.label.toLowerCase()));
const missing = cases.filter((testCase) => ![...labels].some((label) => {
  const prefix = testCase.path.split("?")[0].replace(/^\//, "").split("/").slice(0, 2).join("/");
  return label.includes(prefix);
}));

if (missing.length > 0) {
  console.error(`contract cases are not represented in manifest: ${missing.map((item) => item.label).join(", ")}`);
  process.exit(1);
}

console.log(`contract inventory ok: ${cases.length} cases are represented; this does not establish runtime parity`);
