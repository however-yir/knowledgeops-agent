import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { promisify } from "node:util";

import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { env } from "../config/env.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
import { PlatformStore } from "../platform/platform.store.js";

const execFileAsync = promisify(execFile);

@Controller("ai/harness")
export class HarnessController {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly businessTools: BusinessToolsService
  ) {}

  @Get("actions")
  actions() {
    return [
      {
        action: "query_school",
        runtime: "builtin",
        requiredKeys: [],
        optionalKeys: [],
        riskLevel: "read",
        trustedOnly: false
      },
      {
        action: "query_course",
        runtime: "builtin",
        requiredKeys: [],
        optionalKeys: ["type", "edu", "sorts"],
        riskLevel: "read",
        trustedOnly: false
      },
      {
        action: "add_course_reservation",
        runtime: "builtin",
        requiredKeys: ["course", "studentName", "contactInfo", "school"],
        optionalKeys: ["remark"],
        riskLevel: "write",
        trustedOnly: false,
        sensitiveKeys: ["contactInfo"]
      },
      {
        action: "rag_search",
        runtime: "builtin",
        requiredKeys: [],
        optionalKeys: ["query", "tenantId", "chatId"],
        riskLevel: "read",
        trustedOnly: false
      },
      {
        action: "workspace_list_files",
        runtime: "workspace",
        requiredKeys: [],
        optionalKeys: ["path", "maxDepth"],
        riskLevel: "read",
        trustedOnly: true
      },
      {
        action: "workspace_read_file",
        runtime: "workspace",
        requiredKeys: ["path"],
        optionalKeys: ["maxBytes"],
        riskLevel: "read",
        trustedOnly: true
      },
      {
        action: "workspace_search_text",
        runtime: "workspace",
        requiredKeys: ["query"],
        optionalKeys: ["path", "maxMatches"],
        riskLevel: "read",
        trustedOnly: true
      },
      {
        action: "workspace_diff",
        runtime: "workspace",
        requiredKeys: ["path", "content"],
        optionalKeys: [],
        riskLevel: "write_preview",
        trustedOnly: true
      },
      {
        action: "workspace_propose_patch",
        runtime: "workspace",
        requiredKeys: ["path"],
        optionalKeys: ["content", "patch", "summary"],
        riskLevel: "write_preview",
        trustedOnly: true
      },
      {
        action: "workspace_apply_patch",
        runtime: "workspace",
        requiredKeys: ["path", "content"],
        optionalKeys: ["expectedSha256", "patch", "summary"],
        riskLevel: "write",
        trustedOnly: true
      },
      {
        action: "workspace_run_shell",
        runtime: "workspace",
        requiredKeys: ["command"],
        optionalKeys: ["timeoutSeconds"],
        riskLevel: "shell",
        trustedOnly: true
      },
      {
        action: "mcp_call",
        runtime: "mcp",
        requiredKeys: ["server", "tool", "arguments"],
        optionalKeys: ["url"],
        riskLevel: "external_call",
        trustedOnly: true
      },
      {
        action: "mcp_http_call",
        runtime: "mcp",
        requiredKeys: ["url", "tool"],
        optionalKeys: ["arguments", "server"],
        riskLevel: "external_call",
        trustedOnly: true
      },
      {
        action: "rag_query",
        runtime: "retrieval",
        requiredKeys: ["query"],
        optionalKeys: ["tenantId", "chatId"],
        riskLevel: "read",
        trustedOnly: false
      },
      {
        action: "memory_save",
        runtime: "memory",
        requiredKeys: ["content"],
        optionalKeys: ["tenantId", "userId", "type", "source"],
        riskLevel: "write",
        trustedOnly: true
      },
      {
        action: "graph_search",
        runtime: "graph",
        requiredKeys: ["query"],
        optionalKeys: ["tenantId", "limit"],
        riskLevel: "read",
        trustedOnly: false
      }
    ];
  }

  @Post("actions/preview")
  preview(@Body() request: Record<string, unknown>) {
    const token = newId("ta");
    const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    const decision = evaluatePolicy(request);
    this.store.trustedActions.set(token, { ...request, expiresAt, decision });
    this.store.persist();
    return {
      ok: decision.allowed ? 1 : 0,
      token,
      action: request.action ?? "unknown",
      expiresAt,
      preview: { status: decision.allowed ? "pending_confirmation" : "blocked", request, decision }
    };
  }

  @Post("actions/execute/:token")
  async execute(@Param("token") token: string) {
    const started = Date.now();
    const request = this.store.trustedActions.get(token);
    if (!request) {
      return { status: "not_found", source: "trusted-action" };
    }
    this.store.trustedActions.delete(token);
    if (Date.parse(String(request.expiresAt ?? "")) <= Date.now()) {
      return { status: "expired", source: "trusted-action" };
    }
    const decision = evaluatePolicy(request);
    if (!decision.allowed) {
      return this.record(request, "policy", "blocked", Date.now() - started, { error: decision.message });
    }
    try {
      const observation = await this.executeAction(request);
      return this.record(request, observation.source, "executed", Date.now() - started, observation);
    } catch (error) {
      return this.record(request, "runtime", "error", Date.now() - started, {
        error: error instanceof Error ? error.message : String(error)
      });
    } finally {
      this.store.persist();
    }
  }

  private async executeAction(request: Record<string, unknown>) {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    if (request.action === "query_school") {
      return {
        source: "builtin",
        action: "query_school",
        observation: { status: "success", source: "builtin", data: await this.businessTools.querySchool() }
      };
    }
    if (request.action === "query_course") {
      return {
        source: "builtin",
        action: "query_course",
        observation: { status: "success", source: "builtin", data: await this.businessTools.queryCourse(input) }
      };
    }
    if (request.action === "add_course_reservation") {
      try {
        const result = await this.businessTools.addCourseReservation({
          course: String(input.course ?? ""),
          studentName: String(input.studentName ?? ""),
          contactInfo: String(input.contactInfo ?? ""),
          school: String(input.school ?? ""),
          remark: String(input.remark ?? "")
        });
        return {
          source: "builtin",
          action: "add_course_reservation",
          observation: { source: "builtin", ...result }
        };
      } catch (error) {
        return {
          source: "builtin",
          action: "add_course_reservation",
          observation: {
            status: "error",
            source: "builtin",
            message: error instanceof Error ? error.message : String(error)
          }
        };
      }
    }
    if (request.action === "rag_query" || request.action === "rag_search") {
      const query = String(input.query ?? request.prompt ?? "");
      const tenantId = String(input.tenantId ?? "public");
      const chatId = String(input.chatId ?? "");
      return {
        source: request.action === "rag_search" ? "builtin" : "retrieval",
        action: request.action,
        observation: this.retrievalService.answer(query, tenantId, chatId)
      };
    }
    if (request.action === "workspace_list_files") {
      const path = resolveWorkspacePath(String(input.path ?? "."));
      const maxDepth = Math.max(0, Math.min(Number(input.maxDepth ?? 2), 5));
      return {
        source: "workspace",
        action: "workspace_list_files",
        observation: {
          root: relative(resolve(env.APP_WORKSPACE_ROOT), path) || ".",
          files: listFiles(path, maxDepth)
        }
      };
    }
    if (request.action === "workspace_read_file") {
      const path = resolveWorkspacePath(String(input.path ?? ""));
      const maxBytes = Math.max(1, Math.min(Number(input.maxBytes ?? 20_000), 200_000));
      const content = readFileSync(path, "utf8");
      return {
        source: "workspace",
        action: "workspace_read_file",
        observation: {
          path: relative(resolve(env.APP_WORKSPACE_ROOT), path),
          content: content.slice(0, maxBytes),
          truncated: content.length > maxBytes
        }
      };
    }
    if (request.action === "workspace_search_text") {
      const root = resolveWorkspacePath(String(input.path ?? "."));
      const query = String(input.query ?? "");
      const maxMatches = Math.max(1, Math.min(Number(input.maxMatches ?? 50), 100));
      return {
        source: "workspace",
        action: "workspace_search_text",
        observation: {
          query,
          matches: searchText(root, query, maxMatches)
        }
      };
    }
    if (request.action === "workspace_diff") {
      const path = resolveWorkspacePath(String(input.path ?? ""));
      const current = readFileSync(path, "utf8");
      const proposed = String(input.content ?? "");
      return {
        source: "workspace",
        action: "workspace_diff",
        observation: {
          path: relative(resolve(env.APP_WORKSPACE_ROOT), path),
          currentSha256: sha256(current),
          proposedSha256: sha256(proposed),
          diff: lineDiff(current, proposed)
        }
      };
    }
    if (request.action === "workspace_propose_patch") {
      const path = resolveWorkspacePath(String(input.path ?? ""));
      const current = existsSync(path) ? readFileSync(path, "utf8") : "";
      const proposed = String(input.content ?? "");
      const patch = String(input.patch ?? "");
      return {
        source: "workspace",
        action: "workspace_propose_patch",
        observation: {
          path: relative(resolve(env.APP_WORKSPACE_ROOT), path),
          summary: String(input.summary ?? ""),
          contentBytes: Buffer.byteLength(proposed),
          patch: patch || lineDiff(current, proposed),
          wouldCreate: !existsSync(path),
          applyAction: "workspace_apply_patch"
        }
      };
    }
    if (request.action === "workspace_apply_patch") {
      const path = resolveWorkspacePath(String(input.path ?? ""));
      const current = readFileSync(path, "utf8");
      const expectedSha256 = String(input.expectedSha256 ?? "");
      if (expectedSha256 && expectedSha256 !== sha256(current)) {
        throw new Error("file changed since preview");
      }
      const proposed = String(input.content ?? "");
      writeFileSync(path, proposed);
      return {
        source: "workspace",
        action: "workspace_apply_patch",
        observation: {
          path: relative(resolve(env.APP_WORKSPACE_ROOT), path),
          previousSha256: sha256(current),
          newSha256: sha256(proposed),
          diff: lineDiff(current, proposed)
        }
      };
    }
    if (request.action === "workspace_run_shell") {
      return {
        source: "workspace",
        action: "workspace_run_shell",
        observation: await runShell(String(input.command ?? ""), Number(input.timeoutSeconds ?? env.APP_WORKSPACE_COMMAND_TIMEOUT_SECONDS))
      };
    }
    if (request.action === "mcp_call" || request.action === "mcp_http_call") {
      const url = String(input.url ?? "");
      assertMcpAllowed(url);
      const response = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tool: input.tool, arguments: input.arguments ?? {} })
      });
      const payload = await response.text();
      return {
        source: "mcp",
        action: request.action,
        observation: {
          server: input.server,
          tool: input.tool,
          statusCode: response.status,
          ok: response.ok,
          body: payload.slice(0, 20_000)
        }
      };
    }
    if (request.action === "memory_save") {
      const content = String(input.content ?? "").trim();
      if (!content) {
        throw new Error("content is required");
      }
      const now = nowIso();
      const item = {
        memoryId: newId("mem"),
        tenantId: String(input.tenantId ?? "public"),
        userId: String(input.userId ?? "agent"),
        type: String(input.type ?? "task"),
        content,
        source: String(input.source ?? "agent-harness"),
        confidence: 0.85,
        createdAt: now,
        updatedAt: now
      };
      this.store.memoryItems.push(item);
      return { source: "memory", action: "memory_save", observation: item };
    }
    if (request.action === "graph_search") {
      const query = String(input.query ?? "").toLowerCase();
      const tenantId = String(input.tenantId ?? "public");
      const limit = Math.max(1, Math.min(Number(input.limit ?? 10), 50));
      const entities = this.store.graphEntities
        .filter((entity) => entity.tenantId === tenantId)
        .filter((entity) => `${entity.name} ${entity.description ?? ""} ${entity.aliases.join(" ")}`.toLowerCase().includes(query))
        .slice(0, limit);
      return { source: "graph", action: "graph_search", observation: { entities } };
    }
    return {
      source: "trusted-action",
      action: request.action ?? "unknown",
      observation: { ok: true }
    };
  }

  private record(request: Record<string, unknown>, source: string, status: string, latencyMs: number, observation: unknown) {
    this.store.harnessEvents.push({
      eventId: newId("hevt"),
      action: String(request.action ?? "unknown"),
      source,
      status,
      latencyMs,
      payload: sanitizeObservation(observation),
      createdAt: nowIso()
    });
    return {
      status,
      source,
      action: request.action ?? "unknown",
      observation: sanitizeObservation(observation)
    };
  }
}

function evaluatePolicy(request: Record<string, unknown>): { allowed: boolean; message: string; riskLevel: string } {
  const action = String(request.action ?? "");
  if (!action) {
    return { allowed: false, message: "action is required", riskLevel: "unknown" };
  }
  if (["workspace_list_files", "workspace_read_file", "workspace_search_text", "workspace_diff", "workspace_propose_patch", "workspace_apply_patch"].includes(action)) {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    try {
      resolveWorkspacePath(String(input.path ?? (action === "workspace_list_files" || action === "workspace_search_text" ? "." : "")));
    } catch (error) {
      return { allowed: false, message: error instanceof Error ? error.message : String(error), riskLevel: "blocked" };
    }
  }
  if (action === "workspace_run_shell" && !env.APP_WORKSPACE_SHELL_ENABLED) {
    return { allowed: false, message: "workspace shell is disabled", riskLevel: "shell" };
  }
  if (action === "mcp_call" || action === "mcp_http_call") {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    try {
      assertMcpAllowed(String(input.url ?? ""));
    } catch (error) {
      return { allowed: false, message: error instanceof Error ? error.message : String(error), riskLevel: "external_call" };
    }
  }
  return { allowed: true, message: "allowed", riskLevel: action.includes("apply") || action.includes("save") ? "write" : "read" };
}

function resolveWorkspacePath(value: string): string {
  if (!value.trim()) {
    throw new Error("path is required");
  }
  const root = resolve(env.APP_WORKSPACE_ROOT);
  const target = resolve(root, value);
  if (target !== root && !target.startsWith(`${root}/`)) {
    throw new Error("path escapes workspace root");
  }
  return target;
}

function sanitizeObservation(value: unknown): unknown {
  const text = JSON.stringify(value)
    .replace(/(api[-_]?key|token|authorization)["']?\s*[:=]\s*["']?[^"',}\s]+/gi, "$1=***")
    .slice(0, 20_000);
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function assertMcpAllowed(value: string): void {
  if (!value.trim()) {
    throw new Error("MCP endpoint URL is required");
  }
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("MCP HTTP adapter only supports http(s)");
  }
  const allowlist = env.APP_MCP_HTTP_ALLOWLIST.split(",").map((item) => item.trim()).filter(Boolean);
  if (allowlist.length > 0 && !allowlist.some((prefix) => value.startsWith(prefix))) {
    throw new Error("MCP endpoint is not in APP_MCP_HTTP_ALLOWLIST");
  }
}

function listFiles(root: string, maxDepth: number): Array<Record<string, unknown>> {
  const workspaceRoot = resolve(env.APP_WORKSPACE_ROOT);
  const results: Array<Record<string, unknown>> = [];
  const visit = (path: string, depth: number) => {
    if (results.length >= 200 || depth > maxDepth) {
      return;
    }
    const stat = statSync(path);
    results.push({
      path: relative(workspaceRoot, path) || ".",
      type: stat.isDirectory() ? "directory" : "file",
      size: stat.isFile() ? stat.size : undefined
    });
    if (!stat.isDirectory()) {
      return;
    }
    for (const entry of readdirSync(path).sort()) {
      visit(resolve(path, entry), depth + 1);
      if (results.length >= 200) {
        break;
      }
    }
  };
  visit(root, 0);
  return results;
}

function searchText(root: string, query: string, maxMatches: number): Array<Record<string, unknown>> {
  if (!query) {
    return [];
  }
  const workspaceRoot = resolve(env.APP_WORKSPACE_ROOT);
  const matches: Array<Record<string, unknown>> = [];
  const visit = (path: string, depth: number) => {
    if (matches.length >= maxMatches || depth > 8) {
      return;
    }
    const stat = statSync(path);
    if (stat.isDirectory()) {
      for (const entry of readdirSync(path).sort()) {
        visit(resolve(path, entry), depth + 1);
        if (matches.length >= maxMatches) {
          break;
        }
      }
      return;
    }
    if (!stat.isFile() || stat.size > 1_000_000) {
      return;
    }
    let content = "";
    try {
      content = readFileSync(path, "utf8");
    } catch {
      return;
    }
    const lines = content.split("\n");
    for (let index = 0; index < lines.length && matches.length < maxMatches; index += 1) {
      if (lines[index].includes(query)) {
        matches.push({
          path: relative(workspaceRoot, path),
          lineNumber: index + 1,
          line: lines[index]
        });
      }
    }
  };
  visit(root, 0);
  return matches;
}

async function runShell(commandText: string, timeoutSeconds: number): Promise<Record<string, unknown>> {
  if (!env.APP_WORKSPACE_SHELL_ENABLED) {
    return { status: "error", message: "workspace shell is disabled" };
  }
  const command = commandText.trim().split(/\s+/).filter(Boolean);
  if (!isAllowedCommand(command)) {
    return { status: "error", message: "command is not allowed" };
  }
  const timeout = Math.max(1, Math.min(timeoutSeconds, env.APP_WORKSPACE_COMMAND_TIMEOUT_SECONDS, 30)) * 1000;
  try {
    const { stdout, stderr } = await execFileAsync(command[0], command.slice(1), {
      cwd: resolve(env.APP_WORKSPACE_ROOT),
      timeout,
      maxBuffer: env.APP_WORKSPACE_MAX_COMMAND_OUTPUT_BYTES
    });
    const output = `${stdout}${stderr}`;
    return {
      exitCode: 0,
      stdout,
      stderr,
      output,
      truncated: Buffer.byteLength(output) >= env.APP_WORKSPACE_MAX_COMMAND_OUTPUT_BYTES
    };
  } catch (error) {
    const failure = error as { code?: number | string; stdout?: string; stderr?: string; message?: string };
    return {
      status: "error",
      exitCode: typeof failure.code === "number" ? failure.code : undefined,
      stdout: String(failure.stdout ?? ""),
      stderr: String(failure.stderr ?? failure.message ?? ""),
      output: `${String(failure.stdout ?? "")}${String(failure.stderr ?? failure.message ?? "")}`.slice(0, env.APP_WORKSPACE_MAX_COMMAND_OUTPUT_BYTES)
    };
  }
}

function isAllowedCommand(command: string[]): boolean {
  if (command.length === 0) {
    return false;
  }
  const allowed = new Set(env.APP_WORKSPACE_ALLOWED_COMMANDS.split(",").map((item) => item.trim()).filter(Boolean));
  if (!allowed.has(command[0])) {
    return false;
  }
  if (command[0] === "pwd") {
    return command.length === 1;
  }
  if (command[0] === "git") {
    const subcommands = new Set(env.APP_WORKSPACE_ALLOWED_GIT_SUBCOMMANDS.split(",").map((item) => item.trim()).filter(Boolean));
    return command.length >= 2 && subcommands.has(command[1]);
  }
  return ["ls", "rg"].includes(command[0]);
}

function lineDiff(current: string, proposed: string): string {
  const before = current.split("\n");
  const after = proposed.split("\n");
  const max = Math.max(before.length, after.length);
  const lines: string[] = [];
  for (let index = 0; index < max; index += 1) {
    if (before[index] === after[index]) {
      continue;
    }
    if (before[index] !== undefined) {
      lines.push(`-${before[index]}`);
    }
    if (after[index] !== undefined) {
      lines.push(`+${after[index]}`);
    }
    if (lines.length > 400) {
      lines.push("...diff truncated...");
      break;
    }
  }
  return lines.join("\n");
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
