import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const lock = readFileSync(join(root, "pnpm-lock.yaml"), "utf8");
const packages = [...lock.matchAll(/^ {2}(?! )['"]?([^'":\n]+@[^'":\n]+)['"]?:/gm)]
  .map((match) => match[1])
  .filter((value, index, values) => values.indexOf(value) === index)
  .sort();
const sbom = {
  bomFormat: "CycloneDX-lite",
  specVersion: "1.5",
  metadata: { component: { name: "knowledgeops-agent-typescript" } },
  components: packages.map((purl) => ({ type: "library", name: purl }))
};
writeFileSync(join(root, "sbom.cdx.json"), JSON.stringify(sbom, null, 2));
console.log(`sbom ok: ${packages.length} components`);
