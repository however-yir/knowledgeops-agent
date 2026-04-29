#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";

const repoRoot = process.cwd();
const defaultFramesDir = path.join(os.tmpdir(), "knowledgeops-agent-demo-gif-frames");

const args = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (!arg.startsWith("--")) {
    continue;
  }
  const key = arg.slice(2);
  const next = process.argv[i + 1];
  if (next && !next.startsWith("--")) {
    args.set(key, next);
    i += 1;
  } else {
    args.set(key, "true");
  }
}

const targetUrl = args.get("url") ?? "http://127.0.0.1:5173/";
const framesDir = args.get("frames-dir") ?? defaultFramesDir;
const headless = args.get("headed") !== "true";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function findPlaywrightPackageDir() {
  const explicit = process.env.PLAYWRIGHT_PACKAGE_DIR;
  if (explicit) {
    return explicit;
  }

  const npxRoot = path.join(os.homedir(), ".npm", "_npx");
  try {
    const entries = await fs.readdir(npxRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const moduleDir = path.join(npxRoot, entry.name, "node_modules", "playwright");
      try {
        await fs.access(path.join(moduleDir, "package.json"));
        return moduleDir;
      } catch {
        // Try the next npx cache entry.
      }
    }
  } catch {
    // Fall through to the normal module resolution error.
  }
  return "";
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (importError) {
    const moduleDir = await findPlaywrightPackageDir();
    if (!moduleDir) {
      throw importError;
    }
    const require = createRequire(import.meta.url);
    return require(moduleDir);
  }
}

async function firstExistingPath(paths) {
  for (const candidate of paths) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      // Try the next browser path.
    }
  }
  return "";
}

async function browserLaunchOptions() {
  const executablePath = await firstExistingPath([
    process.env.PLAYWRIGHT_BROWSER_EXECUTABLE ?? "",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
  ].filter(Boolean));

  return executablePath
    ? { headless, executablePath }
    : { headless };
}

function jsonResponse(payload) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload)
  };
}

function sseEvent(event, payload) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

async function ensureCleanDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await fs.mkdir(dir, { recursive: true });
}

async function sha256(filePath) {
  const bytes = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

async function main() {
  const { chromium } = await loadPlaywright();
  await ensureCleanDir(framesDir);

  const browser = await chromium.launch(await browserLaunchOptions());
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce"
  });

  await context.addInitScript(() => {
    localStorage.clear();
  });

  const page = await context.newPage();

  await page.route("**/api/auth/token", async (route) => {
    await wait(180);
    await route.fulfill(jsonResponse({
      ok: 1,
      msg: "ok",
      token: "demo-recording-jwt",
      refreshToken: "demo-recording-refresh",
      tenantId: "tenant-acme",
      expiresInSeconds: 7200
    }));
  });

  await page.route("**/api/auth/refresh", async (route) => {
    await route.fulfill(jsonResponse({
      ok: 1,
      msg: "ok",
      token: "demo-recording-jwt-refreshed",
      refreshToken: "demo-recording-refresh",
      tenantId: "tenant-acme",
      expiresInSeconds: 7200
    }));
  });

  await page.route("**/api/cost/summary", async (route) => {
    await route.fulfill(jsonResponse({
      tenantId: "tenant-acme",
      month: "2026-04",
      monthlyBudgetUsd: 25,
      hardLimitEnabled: false,
      monthCostUsd: 1.2745,
      monthRequestCount: 184,
      monthInputTokens: 92000,
      monthOutputTokens: 31000,
      todayCostUsd: 0.1432,
      todayRequestCount: 18,
      budgetRemainingUsd: 23.7255,
      budgetExceeded: false
    }));
  });

  await page.route("**/api/ai/feedback", async (route) => {
    await wait(220);
    await route.fulfill(jsonResponse({ ok: 1, msg: "feedback accepted" }));
  });

  await page.route("**/api/ai/react/chat/stream", async (route) => {
    await wait(1250);
    const body = [
      sseEvent("trace", {
        step: 1,
        thought: "Resolve tenant context before retrieval.",
        action: "tenant_scope_check",
        actionInput: { tenantId: "tenant-acme" },
        observation: { status: "allowed" }
      }),
      sseEvent("trace", {
        step: 2,
        thought: "Search indexed policy chunks and keep citations.",
        action: "rag_search",
        actionInput: { query: "高温作业健康风险控制要求" },
        observation: {
          status: "success",
          citations: ["source=heat-safety-policy.pdf, chunk=2"]
        }
      }),
      sseEvent("token", { token: "高温作业风险控制建议：" }),
      sseEvent("done", {
        ok: 1,
        msg: "ok",
        chatId: "heat-safety-demo",
        answer: [
          "高温作业风险控制建议：",
          "",
          "1. 先按岗位暴露等级做分级管控，重点覆盖户外巡检、仓储装卸和长时间无空调场景。",
          "2. 入库文档命中后，回答必须带来源引用，便于安全主管复核制度原文。",
          "3. 当检索不到资料时，系统应明确提示“当前知识库无匹配内容”，避免编造政策结论。"
        ].join("\n"),
        citations: [
          "source=heat-safety-policy.pdf, chunk=2",
          "source=heat-safety-policy.pdf, chunk=5",
          "source=operations-runbook.pdf, chunk=1"
        ],
        evidence: [
          "岗位暴露等级需要结合温度、时长、劳动强度和防护条件判定。",
          "高温时段应安排补水、轮换休息、异常上报和现场急救预案。",
          "无命中结果必须触发空结果兜底，不允许输出未引用结论。"
        ],
        routeProfile: "balanced",
        routeReason: "endpoint profile: rag",
        routeCostTier: "medium",
        trace: [
          {
            step: 1,
            thought: "Resolve tenant context before retrieval.",
            action: "tenant_scope_check",
            actionInput: { tenantId: "tenant-acme" },
            observation: { status: "allowed" }
          },
          {
            step: 2,
            thought: "Search indexed policy chunks and keep citations.",
            action: "rag_search",
            actionInput: { query: "高温作业健康风险控制要求" },
            observation: {
              status: "success",
              citations: ["source=heat-safety-policy.pdf, chunk=2"]
            }
          }
        ]
      })
    ].join("");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      headers: {
        "Cache-Control": "no-cache"
      },
      body
    });
  });

  await page.goto(targetUrl, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        transition-duration: 0s !important;
        animation-duration: 0s !important;
        caret-color: transparent !important;
      }
      .el-message {
        box-shadow: 0 12px 32px rgba(18, 32, 51, 0.16) !important;
      }
    `
  });
  await wait(650);

  const frames = [];
  async function capture(name) {
    await wait(120);
    const framePath = path.join(framesDir, `${String(frames.length + 1).padStart(3, "0")}-${name}.png`);
    await page.screenshot({ path: framePath, animations: "disabled" });
    frames.push(framePath);
  }

  await capture("console-ready");

  await page.getByPlaceholder("输入 API Key（生产建议短时使用）").fill("demo-local-api-key");
  await page.getByPlaceholder("public").fill("tenant-acme");
  await capture("auth-filled");

  await page.getByRole("button", { name: "换取 JWT" }).click();
  await page.getByText("JWT 获取成功").waitFor({ state: "visible", timeout: 5000 });
  await capture("jwt-success");

  const composer = page.getByPlaceholder("输入问题，Enter 发送，Shift + Enter 换行");
  await composer.fill("根据上传的高温作业政策 PDF，");
  await capture("question-part-1");
  await composer.fill("根据上传的高温作业政策 PDF，总结健康风险控制要求，");
  await capture("question-part-2");
  await composer.fill("根据上传的高温作业政策 PDF，总结健康风险控制要求，并给出引用来源。");
  await capture("question-ready");

  await page.getByRole("button", { name: "发送" }).click();
  await page.getByText("模型正在准备响应", { exact: true }).first().waitFor({ state: "visible", timeout: 5000 });
  await capture("request-pending");

  await page.getByText("来源引用", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByText("source=heat-safety-policy.pdf, chunk=2", { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });
  await capture("rag-citations");

  await page.getByRole("button", { name: "👍有帮助" }).last().click();
  await page.getByText("反馈已提交并回灌评测集").waitFor({ state: "visible", timeout: 5000 });
  await capture("feedback-submitted");

  await page.getByRole("button", { name: "从当前分叉" }).click();
  await page.getByText("已创建分支").waitFor({ state: "visible", timeout: 5000 });
  await capture("branch-created");

  const hashes = new Map();
  const manifest = [];
  for (const frame of frames) {
    const digest = await sha256(frame);
    const duplicateOf = hashes.get(digest);
    if (duplicateOf) {
      throw new Error(`Duplicate frame detected: ${path.basename(frame)} duplicates ${path.basename(duplicateOf)}`);
    }
    hashes.set(digest, frame);
    manifest.push({ frame, sha256: digest });
  }
  await fs.writeFile(path.join(framesDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  await browser.close();

  console.log(`Captured ${frames.length} unique frames`);
  console.log(framesDir);
  for (const item of manifest) {
    console.log(`${path.basename(item.frame)} ${item.sha256.slice(0, 12)}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
