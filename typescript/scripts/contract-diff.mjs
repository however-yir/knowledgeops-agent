import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const cases = JSON.parse(readFileSync(join(root, "parity", "contract-cases.json"), "utf8"));
const javaBaseUrl = process.env.APP_JAVA_BASE_URL || "";
const tsBaseUrl = process.env.APP_TS_BASE_URL || "";

if (!javaBaseUrl || !tsBaseUrl) {
  const manifest = JSON.parse(readFileSync(join(root, "parity", "manifest.json"), "utf8"));
  const labels = new Set(manifest.requiredRoutes.map((route) => route.label.toLowerCase()));
  const missing = cases.filter((testCase) => ![...labels].some((label) => label.includes(testCase.path.split("?")[0].replace(/^\//, "").split("/").slice(0, 2).join("/"))));
  if (missing.length > 0) {
    console.error(`contract cases are not represented in manifest: ${missing.map((item) => item.label).join(", ")}`);
    process.exit(1);
  }
  console.log(`contract diff static ok: ${cases.length} cases; set APP_JAVA_BASE_URL and APP_TS_BASE_URL for live Java-vs-TS comparison`);
  process.exit(0);
}

const failures = [];
for (const testCase of cases) {
  const [javaResult, tsResult] = await Promise.all([
    call(javaBaseUrl, testCase),
    call(tsBaseUrl, testCase)
  ]);
  const issues = compare(testCase, javaResult, tsResult);
  if (issues.length > 0) {
    failures.push({ label: testCase.label, issues });
  }
}

if (failures.length > 0) {
  for (const failure of failures) {
    console.error(`contract mismatch: ${failure.label}`);
    for (const issue of failure.issues) {
      console.error(`  - ${issue}`);
    }
  }
  process.exit(1);
}

console.log(`contract diff live ok: ${cases.length} Java-vs-TS cases`);

async function call(baseUrl, testCase) {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}${testCase.path}`, {
    method: testCase.method,
    headers: {
      "content-type": "application/json",
      "x-tenant-id": "public",
      ...(testCase.headers ?? {}),
      ...(process.env.APP_CONTRACT_API_KEY ? { "x-api-key": process.env.APP_CONTRACT_API_KEY } : {})
    },
    body: testCase.body ? JSON.stringify(testCase.body) : undefined
  });
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();
  return {
    status: response.status,
    contentType: normalizeContentType(contentType),
    schema: testCase.sse ? sseSchema(text) : jsonSchema(text)
  };
}

function compare(testCase, javaResult, tsResult) {
  const issues = [];
  if (javaResult.status !== tsResult.status) {
    issues.push(`status ${javaResult.status} != ${tsResult.status}`);
  }
  if (testCase.expectStatus && tsResult.status !== testCase.expectStatus) {
    issues.push(`TS status ${tsResult.status} != expected ${testCase.expectStatus}`);
  }
  if (javaResult.contentType !== tsResult.contentType) {
    issues.push(`content-type ${javaResult.contentType} != ${tsResult.contentType}`);
  }
  if (JSON.stringify(javaResult.schema) !== JSON.stringify(tsResult.schema)) {
    issues.push(`body schema ${JSON.stringify(javaResult.schema)} != ${JSON.stringify(tsResult.schema)}`);
  }
  return issues;
}

function normalizeContentType(value) {
  if (value.includes("text/event-stream")) {
    return "text/event-stream";
  }
  if (value.includes("application/json")) {
    return "application/json";
  }
  if (value.includes("text/html")) {
    return "text/html";
  }
  if (value.includes("text/plain")) {
    return "text/plain";
  }
  return value.split(";")[0] || "unknown";
}

function jsonSchema(text) {
  try {
    return schemaOf(JSON.parse(text));
  } catch {
    return { type: "text" };
  }
}

function sseSchema(text) {
  return text
    .split(/\n\n/)
    .filter(Boolean)
    .map((chunk) => ({
      event: (chunk.match(/^event:\s*(.+)$/m)?.[1] || "message").trim(),
      data: jsonSchema((chunk.match(/^data:\s*(.+)$/m)?.[1] || "").trim())
    }));
}

function schemaOf(value) {
  if (Array.isArray(value)) {
    return { type: "array", items: value.length ? schemaOf(value[0]) : "unknown" };
  }
  if (value && typeof value === "object") {
    return {
      type: "object",
      keys: Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, schemaOf(child)]))
    };
  }
  return { type: typeof value };
}
