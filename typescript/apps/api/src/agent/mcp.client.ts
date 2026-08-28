import { randomUUID } from "node:crypto";
import { lookup as dnsLookup } from "node:dns/promises";

import { Injectable } from "@nestjs/common";

import { env } from "../config/env.js";

const MCP_PROTOCOL_VERSION = "2024-11-05";

export interface McpToolDefinition {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  annotations?: Record<string, unknown>;
}

interface McpServerConfig {
  id: string;
  endpoint: string;
  headers: Record<string, string>;
  timeoutMs: number;
  allowedTools: Set<string>;
}

interface McpSession {
  sessionId?: string;
}

interface JsonRpcResponse<T> {
  jsonrpc?: string;
  id?: string | number | null;
  result?: T;
  error?: { code?: number; message?: string; data?: unknown };
}

interface ToolsListResult {
  tools?: unknown[];
  nextCursor?: string;
}

@Injectable()
export class McpClient {
  private readonly sessions = new Map<string, Promise<McpSession>>();

  assertConfigured(server: string, tool?: string): void {
    const config = this.server(server);
    if (tool && !config.allowedTools.has(tool)) {
      throw new Error(`MCP tool is not allowed: ${server}/${tool}`);
    }
  }

  async listTools(server: string): Promise<McpToolDefinition[]> {
    const config = this.server(server);
    await assertSafeMcpEndpoint(config.endpoint, parseAllowedHosts(env.APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS));
    const session = await this.initialize(config);
    const tools: McpToolDefinition[] = [];
    let cursor: string | undefined;
    for (let page = 0; page < 100; page += 1) {
      const result = await this.rpc<ToolsListResult>(config, session, "tools/list", cursor ? { cursor } : {});
      for (const value of result.tools ?? []) {
        const tool = parseTool(value);
        if (tool && config.allowedTools.has(tool.name)) tools.push(tool);
      }
      if (!result.nextCursor) return deduplicateTools(tools);
      cursor = result.nextCursor;
    }
    throw new Error(`MCP tools/list pagination exceeded 100 pages for ${server}`);
  }

  async callTool(server: string, tool: string, args: Record<string, unknown>): Promise<unknown> {
    const config = this.server(server);
    if (!config.allowedTools.has(tool)) throw new Error(`MCP tool is not allowed: ${server}/${tool}`);
    await assertSafeMcpEndpoint(config.endpoint, parseAllowedHosts(env.APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS));
    const advertised = await this.listTools(server);
    if (!advertised.some((candidate) => candidate.name === tool)) {
      throw new Error(`MCP server did not advertise tool: ${server}/${tool}`);
    }
    const session = await this.initialize(config);
    return this.rpc(config, session, "tools/call", { name: tool, arguments: args });
  }

  private initialize(config: McpServerConfig): Promise<McpSession> {
    const key = `${config.id}:${config.endpoint}`;
    let pending = this.sessions.get(key);
    if (!pending) {
      pending = this.startSession(config).catch((error) => {
        this.sessions.delete(key);
        throw error;
      });
      this.sessions.set(key, pending);
    }
    return pending;
  }

  private async startSession(config: McpServerConfig): Promise<McpSession> {
    const response = await this.request(config, undefined, {
      jsonrpc: "2.0",
      id: randomUUID(),
      method: "initialize",
      params: {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "knowledgeops-api", version: "0.1.0" }
      }
    });
    const payload = parseRpcPayload(response.body, response.contentType);
    assertRpcResponse(payload, response.requestId);
    if (!isRecord(payload.result)) throw new Error("MCP initialize response is missing result");
    const protocolVersion = clean(payload.result.protocolVersion);
    if (!protocolVersion) throw new Error("MCP initialize response is missing protocolVersion");
    const session = { sessionId: response.sessionId };
    await this.notification(config, session, "notifications/initialized");
    return session;
  }

  private async rpc<T>(config: McpServerConfig, session: McpSession, method: "tools/list" | "tools/call", params: Record<string, unknown>): Promise<T> {
    const response = await this.request(config, session, { jsonrpc: "2.0", id: randomUUID(), method, params });
    const payload = parseRpcPayload(response.body, response.contentType);
    assertRpcResponse(payload, response.requestId);
    return payload.result as T;
  }

  private async notification(config: McpServerConfig, session: McpSession, method: string): Promise<void> {
    const response = await fetch(config.endpoint, {
      method: "POST",
      headers: requestHeaders(config, session),
      body: JSON.stringify({ jsonrpc: "2.0", method }),
      signal: AbortSignal.timeout(config.timeoutMs)
    });
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`MCP HTTP ${response.status}: ${body.slice(0, 1000) || response.statusText}`);
    }
  }

  private async request(
    config: McpServerConfig,
    session: McpSession | undefined,
    payload: { jsonrpc: "2.0"; id: string; method: string; params: Record<string, unknown> }
  ): Promise<{ body: string; contentType: string | null; requestId: string; sessionId?: string }> {
    const response = await fetch(config.endpoint, {
      method: "POST",
      headers: requestHeaders(config, session),
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(config.timeoutMs)
    });
    const body = await response.text();
    if (!response.ok) {
      throw new Error(`MCP HTTP ${response.status}: ${body.slice(0, 1000) || response.statusText}`);
    }
    return {
      body,
      contentType: response.headers.get("content-type"),
      requestId: payload.id,
      sessionId: response.headers.get("mcp-session-id") ?? session?.sessionId
    };
  }

  private server(serverId: string): McpServerConfig {
    const id = serverId.trim();
    if (!id) throw new Error("MCP server is required");
    const root = parseObject(env.APP_MCP_SERVERS_JSON, "APP_MCP_SERVERS_JSON");
    const servers = isRecord(root.servers) ? root.servers : root;
    const raw = servers[id];
    if (!isRecord(raw) || raw.enabled === false) throw new Error(`MCP server is not configured or enabled: ${id}`);
    const endpoint = endpointFrom(raw);
    const url = new URL(endpoint);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error(`MCP server ${id} must use http(s)`);
    const tools = allowedTools(raw);
    if (tools.size === 0) throw new Error(`MCP server ${id} requires a non-empty tool allowlist`);
    return {
      id,
      endpoint: url.toString(),
      headers: stringRecord(raw.headers),
      timeoutMs: finiteInteger(raw.timeoutMs, 10_000, 1, 120_000),
      allowedTools: tools
    };
  }
}

function requestHeaders(config: McpServerConfig, session?: McpSession): Record<string, string> {
  return {
    ...config.headers,
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
    ...(session?.sessionId ? { "mcp-session-id": session.sessionId } : {})
  };
}

function assertRpcResponse(payload: JsonRpcResponse<unknown>, requestId: string): void {
  if (payload.jsonrpc !== "2.0") throw new Error("MCP response is not JSON-RPC 2.0");
  if (String(payload.id) !== requestId) throw new Error("MCP response id does not match request id");
  if (payload.error) {
    const code = payload.error.code === undefined ? "unknown" : payload.error.code;
    throw new Error(`MCP JSON-RPC error ${code}: ${payload.error.message || "request failed"}`);
  }
  if (!("result" in payload)) throw new Error("MCP JSON-RPC response is missing result");
}

function endpointFrom(raw: Record<string, unknown>): string {
  const direct = clean(raw.endpoint) || clean(raw.url);
  if (direct) return direct;
  const baseUrl = clean(raw.baseUrl);
  if (!baseUrl) throw new Error("configured MCP server requires endpoint, url, or baseUrl");
  const path = clean(raw.path);
  return path ? new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString() : baseUrl;
}

function allowedTools(raw: Record<string, unknown>): Set<string> {
  const explicit = Array.isArray(raw.allowedTools) ? raw.allowedTools.map(clean).filter(Boolean) : [];
  if (explicit.length > 0) return new Set(explicit);
  if (Array.isArray(raw.tools)) return new Set(raw.tools.map(clean).filter(Boolean));
  if (isRecord(raw.tools)) {
    return new Set(Object.entries(raw.tools)
      .filter(([, config]) => config === true || (isRecord(config) && config.enabled !== false))
      .map(([name]) => name.trim())
      .filter(Boolean));
  }
  return new Set();
}

function parseRpcPayload(body: string, contentType: string | null): JsonRpcResponse<unknown> {
  const trimmed = body.trim();
  if (!trimmed) throw new Error("MCP response body is empty");
  if (contentType?.toLowerCase().includes("text/event-stream") || trimmed.startsWith("event:") || trimmed.startsWith("data:")) {
    const payloads = trimmed
      .replace(/\r\n/g, "\n")
      .split("\n\n")
      .map((event) => event.split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n"))
      .filter(Boolean);
    if (payloads.length === 0) throw new Error("MCP SSE response has no data event");
    return parseJson(payloads.at(-1)!, "MCP SSE data");
  }
  return parseJson(trimmed, "MCP response");
}

function parseTool(value: unknown): McpToolDefinition | undefined {
  if (!isRecord(value) || !clean(value.name)) return undefined;
  return {
    name: clean(value.name),
    ...(clean(value.description) ? { description: clean(value.description) } : {}),
    ...(isRecord(value.inputSchema) ? { inputSchema: value.inputSchema } : {}),
    ...(isRecord(value.outputSchema) ? { outputSchema: value.outputSchema } : {}),
    ...(isRecord(value.annotations) ? { annotations: value.annotations } : {})
  };
}

function deduplicateTools(tools: McpToolDefinition[]): McpToolDefinition[] {
  return [...new Map(tools.map((tool) => [tool.name, tool])).values()];
}

function parseObject(value: string, label: string): Record<string, unknown> {
  const parsed = parseJson(value, label);
  if (!isRecord(parsed)) throw new Error(`${label} must contain a JSON object`);
  return parsed;
}

function parseJson(value: string, label: string): any {
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${label} contains invalid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function finiteInteger(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= min && parsed <= max ? parsed : fallback;
}

function clean(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseAllowedHosts(raw: string): string[] {
  return raw.split(",").map((host) => host.trim()).filter(Boolean);
}

export function hostMatchesAllowList(host: string, allowedHosts: string[]): boolean {
  const normalized = host.toLowerCase();
  return allowedHosts.some((pattern) => {
    const candidate = pattern.trim().toLowerCase();
    if (!candidate) return false;
    return candidate.startsWith(".") ? normalized.endsWith(candidate) : candidate === normalized;
  });
}

/**
 * Refuse addresses an outbound MCP call must never reach: loopback, the
 * unspecified address, RFC1918 private ranges, IPv6 ULA, link-local
 * (including the cloud-metadata range 169.254.0.0/16), and multicast.
 */
export function isRestrictedMcpAddress(raw: string): boolean {
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/.exec(raw.trim().toLowerCase());
  const address = mapped ? mapped[1] : raw.trim().toLowerCase();
  if (address === "::" || address === "::1" || address === "0:0:0:0:0:0:0:1") return true;
  if (address.includes(":")) {
    return /^fe[89ab]/.test(address) || /^fe[c-f]/.test(address) || /^f[cd]/.test(address) || /^ff/.test(address);
  }
  const octets = address.split(".").map((octet) => Number(octet));
  if (octets.length !== 4 || octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) return false;
  const [first, second] = octets as [number, number];
  if (first === 0 || first === 10 || first === 127) return true;
  if (first === 169 && second === 254) return true;
  if (first === 172 && second >= 16 && second <= 31) return true;
  if (first === 192 && second === 168) return true;
  return first >= 224 && first <= 239;
}

/**
 * Refuse MCP endpoints whose host resolves to a restricted address so an
 * agent invocation of mcp_call / mcp_http_call cannot be turned into an
 * SSRF probe against internal services or the cloud metadata API.
 * Operators can exempt curated hosts (exact or ".suffix" match) via
 * APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS; resolution failure fails closed.
 */
export async function assertSafeMcpEndpoint(
  endpoint: string,
  allowedHosts: string[],
  resolveHost: (host: string) => Promise<{ address: string }[]> = (host) => dnsLookup(host, { all: true, verbatim: true })
): Promise<void> {
  const url = new URL(endpoint);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error(`MCP endpoint must use http(s): ${endpoint}`);
  }
  if (hostMatchesAllowList(url.hostname, allowedHosts)) return;
  let addresses: { address: string }[];
  try {
    addresses = await resolveHost(url.hostname);
  } catch {
    throw new Error(`MCP endpoint host could not be resolved: ${url.hostname}`);
  }
  if (addresses.length === 0) {
    throw new Error(`MCP endpoint host could not be resolved: ${url.hostname}`);
  }
  for (const { address } of addresses) {
    if (isRestrictedMcpAddress(address)) {
      throw new Error(`MCP endpoint host resolves to a restricted private/loopback/link-local/multicast address: ${url.hostname}`);
    }
  }
}
