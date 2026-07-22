import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const cases = JSON.parse(readFileSync(join(root, "parity", "contract-cases.json"), "utf8"));
const javaBaseUrl = process.env.APP_JAVA_BASE_URL?.trim();
const tsBaseUrl = process.env.APP_TS_BASE_URL?.trim();

if (!javaBaseUrl || !tsBaseUrl) {
  console.error("live contract diff requires APP_JAVA_BASE_URL and APP_TS_BASE_URL; use contract:inventory for static checks");
  process.exit(1);
}

const failures = [];
for (const testCase of cases) {
  try {
    const [javaResult, tsResult] = await Promise.all([
      call(javaBaseUrl, testCase),
      call(tsBaseUrl, testCase)
    ]);
    const issues = compare(testCase, javaResult, tsResult);
    if (issues.length > 0) {
      failures.push({ label: testCase.label, issues });
    }
  } catch (error) {
    failures.push({
      label: testCase.label,
      issues: [error instanceof Error ? error.message : String(error)]
    });
  }
}

if (failures.length > 0) {
  for (const failure of failures) {
    console.error(`contract mismatch: ${failure.label}`);
    for (const issue of failure.issues) {
      console.error(`  - ${issue}`);
    }
  }
  console.error(`live contract diff failed: ${failures.length}/${cases.length} cases mismatched`);
  process.exit(1);
}

console.log(`contract diff live ok: ${cases.length} Java-vs-TS cases`);

async function call(baseUrl, testCase) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(testCase.timeoutMs ?? 30_000));
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}${testCase.path}`, {
      method: testCase.method,
      headers: {
        "content-type": "application/json",
        "x-tenant-id": testCase.tenantId ?? "public",
        ...(testCase.headers ?? {}),
        ...(process.env.APP_CONTRACT_API_KEY ? { "x-api-key": process.env.APP_CONTRACT_API_KEY } : {})
      },
      body: testCase.body === undefined ? undefined : JSON.stringify(testCase.body),
      signal: controller.signal
    });
    const bytes = Buffer.from(await response.arrayBuffer());
    const contentType = normalizeContentType(response.headers.get("content-type") ?? "");
    return {
      status: response.status,
      contentType,
      headers: significantHeaders(response.headers),
      body: parseBody(bytes, contentType, testCase),
      hash: sha256(bytes)
    };
  } catch (error) {
    throw new Error(`${baseUrl} ${testCase.method} ${testCase.path}: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    clearTimeout(timeout);
  }
}

function compare(testCase, javaResult, tsResult) {
  const issues = [];
  if (javaResult.status !== tsResult.status) {
    issues.push(`status Java=${javaResult.status} TS=${tsResult.status}`);
  }
  if (testCase.expectStatus !== undefined) {
    if (javaResult.status !== testCase.expectStatus) {
      issues.push(`Java status ${javaResult.status} != expected ${testCase.expectStatus}`);
    }
    if (tsResult.status !== testCase.expectStatus) {
      issues.push(`TS status ${tsResult.status} != expected ${testCase.expectStatus}`);
    }
  }
  if (javaResult.contentType !== tsResult.contentType) {
    issues.push(`content-type Java=${javaResult.contentType} TS=${tsResult.contentType}`);
  }
  for (const name of new Set([...Object.keys(javaResult.headers), ...Object.keys(tsResult.headers)])) {
    if ((javaResult.headers[name] ?? null) !== (tsResult.headers[name] ?? null)) {
      issues.push(`header ${name} Java=${JSON.stringify(javaResult.headers[name])} TS=${JSON.stringify(tsResult.headers[name])}`);
    }
  }
  if (testCase.binary) {
    if (javaResult.hash !== tsResult.hash) {
      issues.push(`binary sha256 Java=${javaResult.hash} TS=${tsResult.hash}`);
    }
    return issues;
  }
  const ignored = new Set(testCase.ignorePaths ?? []);
  const javaBody = normalizeValue(javaResult.body, "$", ignored);
  const tsBody = normalizeValue(tsResult.body, "$", ignored);
  const bodyIssue = firstDifference(javaBody, tsBody, "$", Number(testCase.maxDiffDepth ?? 20));
  if (bodyIssue) {
    issues.push(bodyIssue);
  }
  return issues;
}

function parseBody(bytes, contentType, testCase) {
  if (testCase.binary) {
    return { byteLength: bytes.length };
  }
  const text = bytes.toString("utf8");
  if (testCase.sse || contentType === "text/event-stream") {
    return parseSse(text);
  }
  if (contentType === "application/json") {
    try {
      return JSON.parse(text);
    } catch {
      return { invalidJson: text };
    }
  }
  return text.replace(/\r\n/g, "\n");
}

function parseSse(text) {
  return text.replace(/\r\n/g, "\n")
    .split(/\n\n+/)
    .filter((frame) => frame.trim())
    .map((frame) => {
      const lines = frame.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() ?? "message";
      const dataText = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      let data = dataText;
      try {
        data = JSON.parse(dataText);
      } catch {
        // Plain text SSE data is part of the observable contract.
      }
      return { event, data };
    });
}

function normalizeValue(value, path, ignored) {
  if (ignored.has(path)) {
    return "<ignored>";
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => normalizeValue(item, `${path}[${index}]`, ignored));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => [key, normalizeValue(child, `${path}.${key}`, ignored)]));
  }
  return value;
}

function firstDifference(left, right, path, depth) {
  if (Object.is(left, right)) {
    return undefined;
  }
  if (depth <= 0) {
    return `${path} differs beyond comparison depth`;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right)) {
      return `${path} type Java=${typeOf(left)} TS=${typeOf(right)}`;
    }
    if (left.length !== right.length) {
      return `${path} length Java=${left.length} TS=${right.length}`;
    }
    for (let index = 0; index < left.length; index += 1) {
      const issue = firstDifference(left[index], right[index], `${path}[${index}]`, depth - 1);
      if (issue) {
        return issue;
      }
    }
    return undefined;
  }
  if (isRecord(left) || isRecord(right)) {
    if (!isRecord(left) || !isRecord(right)) {
      return `${path} type Java=${typeOf(left)} TS=${typeOf(right)}`;
    }
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    if (JSON.stringify(leftKeys) !== JSON.stringify(rightKeys)) {
      return `${path} keys Java=${JSON.stringify(leftKeys)} TS=${JSON.stringify(rightKeys)}`;
    }
    for (const key of leftKeys) {
      const issue = firstDifference(left[key], right[key], `${path}.${key}`, depth - 1);
      if (issue) {
        return issue;
      }
    }
    return undefined;
  }
  return `${path} Java=${JSON.stringify(left)} TS=${JSON.stringify(right)}`;
}

function significantHeaders(headers) {
  const values = {};
  for (const name of ["content-disposition", "x-tenant-id"]) {
    const value = headers.get(name);
    if (value !== null) {
      values[name] = value;
    }
  }
  return values;
}

function normalizeContentType(value) {
  if (value.includes("text/event-stream")) return "text/event-stream";
  if (value.includes("application/json")) return "application/json";
  if (value.includes("text/html")) return "text/html";
  if (value.includes("text/plain")) return "text/plain";
  if (value.includes("application/octet-stream")) return "application/octet-stream";
  return value.split(";")[0] || "unknown";
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function typeOf(value) {
  return Array.isArray(value) ? "array" : value === null ? "null" : typeof value;
}
