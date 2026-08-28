import { Body, Controller, Get, Param, Post } from "@nestjs/common";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { promisify } from "node:util";

import { RetrievalService } from "../ai/retrieval.service.js";
import { newId, nowIso } from "../common/ids.js";
import { TenantId } from "../common/tenant-id.decorator.js";
import { env } from "../config/env.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { McpClient } from "./mcp.client.js";

const execFileAsync = promisify(execFile);

@Controller("ai/harness")
export class HarnessController {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly businessTools: BusinessToolsService,
    private readonly mcpClient: McpClient
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
        action: "mcp_tools_list",
        runtime: "mcp",
        requiredKeys: ["server"],
        optionalKeys: [],
        riskLevel: "external_call",
        trustedOnly: true
      },
      {
        action: "mcp_call",
        runtime: "mcp",
        requiredKeys: ["server", "tool"],
        optionalKeys: ["arguments"],
        riskLevel: "external_call",
        trustedOnly: true
      },
      {
        action: "mcp_http_call",
        runtime: "mcp",
        requiredKeys: ["server", "tool"],
        optionalKeys: ["arguments"],
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
  preview(@TenantId() tenantId: string, @Body() request: Record<string, unknown>) {
    const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    const trustedRequest = { ...request, tenantId };
    let decision = evaluatePolicy(trustedRequest);
    if (decision.allowed && ["mcp_tools_list", "mcp_call", "mcp_http_call"].includes(String(request.action ?? ""))) {
      const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
      try {
        this.mcpClient.assertConfigured(
          String(input.server ?? ""),
          request.action === "mcp_tools_list" ? undefined : String(input.tool ?? "")
        );
      } catch (error) {
        decision = {
          allowed: false,
          message: error instanceof Error ? error.message : String(error),
          riskLevel: "external_call"
        };
      }
    }
    if (!decision.allowed) {
      return {
        ok: 0,
        action: request.action ?? "unknown",
        preview: { status: "blocked", request: trustedRequest, decision }
      };
    }
    const token = newId("ta");
    this.store.trustedActions.set(token, { ...trustedRequest, expiresAt, decision });
    this.store.persist();
    return {
      ok: 1,
      token,
      action: request.action ?? "unknown",
      expiresAt,
      preview: { status: "pending_confirmation", request: trustedRequest, decision }
    };
  }

  @Post("actions/execute/:token")
  async execute(@TenantId() tenantId: string, @Param("token") token: string) {
    const started = Date.now();
    const request = this.store.trustedActions.get(token);
    if (!request || request.tenantId !== tenantId) {
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
    const input: Record<string, unknown> = {
      ...((request.actionInput as Record<string, unknown> | undefined) ?? request),
      tenantId: request.tenantId
    };
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
    if (request.action === "mcp_tools_list") {
      const server = String(input.server ?? "").trim();
      return {
        source: "mcp",
        action: "mcp_tools_list",
        observation: { server, tools: await this.mcpClient.listTools(server) }
      };
    }
    if (request.action === "mcp_call" || request.action === "mcp_http_call") {
      const server = String(input.server ?? "").trim();
      const tool = String(input.tool ?? "").trim();
      const argumentsValue = isRecord(input.arguments) ? input.arguments : {};
      return {
        source: "mcp",
        action: request.action,
        observation: {
          server,
          tool,
          result: await this.mcpClient.callTool(server, tool, argumentsValue)
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
      tenantId: String(request.tenantId ?? "public"),
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
  const trustedActions = new Set([
    "mcp_call",
    "mcp_http_call",
    "mcp_tools_list",
    "workspace_list_files",
    "workspace_read_file",
    "workspace_search_text",
    "workspace_diff",
    "workspace_propose_patch",
    "workspace_apply_patch",
    "workspace_run_shell",
    "memory_save"
  ]);
  if (!trustedActions.has(action)) {
    return { allowed: false, message: `action does not require trusted runtime: ${action}`, riskLevel: "unknown" };
  }
  if (!env.APP_AGENT_HARNESS_TRUSTED_ENABLED) {
    return { allowed: false, message: "trusted runtime is disabled", riskLevel: "blocked" };
  }
  if (["workspace_list_files", "workspace_read_file", "workspace_search_text", "workspace_diff", "workspace_propose_patch", "workspace_apply_patch"].includes(action)) {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    try {
      resolveWorkspacePath(String(input.path ?? (action === "workspace_list_files" || action === "workspace_search_text" ? "." : "")));
    } catch (error) {
      return { allowed: false, message: error instanceof Error ? error.message : String(error), riskLevel: "blocked" };
    }
  }
  if (action === "workspace_apply_patch" && !env.APP_WORKSPACE_WRITE_ENABLED) {
    return { allowed: false, message: "workspace writes are disabled", riskLevel: "write" };
  }
  if (action === "workspace_run_shell" && !env.APP_WORKSPACE_SHELL_ENABLED) {
    return { allowed: false, message: "workspace shell is disabled", riskLevel: "shell" };
  }
  if (action === "mcp_call" || action === "mcp_http_call" || action === "mcp_tools_list") {
    const input = (request.actionInput as Record<string, unknown> | undefined) ?? request;
    if (typeof input.url === "string" && input.url.trim()) {
      return { allowed: false, message: "caller-provided MCP URLs are disabled; use a configured server", riskLevel: "external_call" };
    }
    if (!String(input.server ?? "").trim()) {
      return { allowed: false, message: "MCP server is required", riskLevel: "external_call" };
    }
    if (action !== "mcp_tools_list" && !String(input.tool ?? "").trim()) {
      return { allowed: false, message: "MCP tool is required", riskLevel: "external_call" };
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
    const failure = error as { code?: number | string; killed?: boolean; stdout?: string; stderr?: string; message?: string };
    if (failure.killed) {
      // execFileAsync reaps the child on timeout; surface the same explicit
      // "command timed out" outcome the Java runtime reports.
      return { status: "error", message: "command timed out" };
    }
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
