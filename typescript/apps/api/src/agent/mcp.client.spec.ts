import { afterEach, describe, expect, it, vi } from "vitest";

import { env } from "../config/env.js";
import { hostMatchesAllowList, isRestrictedMcpAddress, McpClient, parseAllowedHosts } from "./mcp.client.js";

const dnsLookup = vi.hoisted(() =>
  vi.fn(async () => [{ address: "93.184.216.34", family: 4 as const }])
);
vi.mock("node:dns/promises", () => ({ lookup: dnsLookup }));

const originalConfig = env.APP_MCP_SERVERS_JSON;
const originalAllowedHosts = env.APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS;

afterEach(() => {
  env.APP_MCP_SERVERS_JSON = originalConfig;
  env.APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS = originalAllowedHosts;
  dnsLookup.mockClear();
  vi.unstubAllGlobals();
});

describe("McpClient", () => {
  it("initializes a configured server, filters tools, and performs tools/call", async () => {
    env.APP_MCP_SERVERS_JSON = JSON.stringify({
      servers: {
        catalog: {
          endpoint: "https://mcp.example.test/rpc",
          headers: { authorization: "Bearer configured-secret" },
          timeoutMs: 2000,
          allowedTools: ["search"]
        }
      }
    });
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (payload.method === "initialize") {
        return rpcResponse(payload.id, {
          protocolVersion: "2024-11-05",
          capabilities: {},
          serverInfo: { name: "catalog", version: "1.0.0" }
        }, { "mcp-session-id": "session-1" });
      }
      if (payload.method === "notifications/initialized") return new Response(null, { status: 202 });
      if (payload.method === "tools/list") {
        return rpcResponse(payload.id, {
          tools: [
            { name: "search", description: "Search catalog", inputSchema: { type: "object" } },
            { name: "admin_delete", description: "Not allowlisted" }
          ]
        });
      }
      return rpcResponse(payload.id, {
        content: [{ type: "text", text: "result" }],
        isError: false
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await new McpClient().callTool("catalog", "search", { query: "safety" });

    expect(result).toMatchObject({ isError: false });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const requests = fetchMock.mock.calls.map(([, init]) => ({
      body: JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>,
      headers: init?.headers as Record<string, string>
    }));
    expect(requests.map((request) => request.body.method)).toEqual([
      "initialize",
      "notifications/initialized",
      "tools/list",
      "tools/call"
    ]);
    expect(requests[2]?.headers["mcp-session-id"]).toBe("session-1");
    expect(requests[3]?.headers.authorization).toBe("Bearer configured-secret");
    expect(requests[3]?.body.params).toEqual({ name: "search", arguments: { query: "safety" } });
  });

  it("parses tools/list from SSE and rejects JSON-RPC errors", async () => {
    env.APP_MCP_SERVERS_JSON = JSON.stringify({
      catalog: { endpoint: "https://mcp.example.test/rpc", allowedTools: ["search"] }
    });
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (payload.method === "initialize") {
        return rpcResponse(payload.id, { protocolVersion: "2024-11-05", capabilities: {} });
      }
      if (payload.method === "notifications/initialized") return new Response(null, { status: 202 });
      return new Response(`event: message\ndata: ${JSON.stringify({
        jsonrpc: "2.0",
        id: payload.id,
        error: { code: -32601, message: "tools/list unavailable" }
      })}\n\n`, { headers: { "content-type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(new McpClient().listTools("catalog")).rejects.toThrow("MCP JSON-RPC error -32601: tools/list unavailable");
  });

  it("requires configured servers and explicit tool allowlists", () => {
    env.APP_MCP_SERVERS_JSON = JSON.stringify({ catalog: { endpoint: "https://mcp.example.test/rpc" } });
    const client = new McpClient();

    expect(() => client.assertConfigured("missing")).toThrow("not configured or enabled");
    expect(() => client.assertConfigured("catalog")).toThrow("requires a non-empty tool allowlist");
  });

  it("refuses endpoints resolving to private/loopback/link-local addresses before any network call", async () => {
    env.APP_MCP_SERVERS_JSON = JSON.stringify({ catalog: { endpoint: "http://metadata.internal/rpc", allowedTools: ["search"] } });
    dnsLookup.mockResolvedValueOnce([{ address: "169.254.169.254", family: 4 as const }]);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(new McpClient().listTools("catalog")).rejects.toThrow("restricted private/loopback/link-local/multicast");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses unresolvable endpoint hosts (fail closed)", async () => {
    env.APP_MCP_SERVERS_JSON = JSON.stringify({ catalog: { endpoint: "https://no-such-host.invalid/rpc", allowedTools: ["search"] } });
    dnsLookup.mockRejectedValueOnce(new Error("ENOTFOUND"));

    await expect(new McpClient().listTools("catalog")).rejects.toThrow("could not be resolved");
  });

  it("lets operator-allowlisted hosts reach private endpoints", async () => {
    env.APP_AGENT_HARNESS_MCP_ALLOWED_HOSTS = "localhost";
    env.APP_MCP_SERVERS_JSON = JSON.stringify({ catalog: { endpoint: "http://localhost:9999/rpc", allowedTools: ["search"] } });
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (payload.method === "initialize") {
        return rpcResponse(payload.id, { protocolVersion: "2024-11-05", capabilities: {} });
      }
      if (payload.method === "notifications/initialized") return new Response(null, { status: 202 });
      return rpcResponse(payload.id, { tools: [{ name: "search" }] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const tools = await new McpClient().listTools("catalog");
    expect(tools.map((tool) => tool.name)).toEqual(["search"]);
  });

  it("classifies restricted addresses across the SSRF rejection matrix", () => {
    const restricted = [
      "127.0.0.1", "127.254.1.2", "10.1.2.3", "172.16.0.1", "172.31.255.255",
      "192.168.1.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "239.255.255.255",
      "::1", "::", "fe80::1", "fec0::1", "fd00::1", "ff02::1", "::ffff:127.0.0.1"
    ];
    const publicAddresses = ["8.8.8.8", "172.32.0.1", "192.169.0.1", "169.255.1.1", "93.184.216.34", "2400:cb00::1"];
    for (const address of restricted) expect(isRestrictedMcpAddress(address), address).toBe(true);
    for (const address of publicAddresses) expect(isRestrictedMcpAddress(address), address).toBe(false);
  });

  it("matches operator allowlists by exact host or dot suffix (subdomains only)", () => {
    expect(hostMatchesAllowList("localhost", ["localhost", "127.0.0.1", "::1"])).toBe(true);
    expect(hostMatchesAllowList("a.internal.example.com", [".internal.example.com"])).toBe(true);
    expect(hostMatchesAllowList("internal.example.com", [".internal.example.com"])).toBe(false);
    expect(hostMatchesAllowList("internal.example.com", ["internal.example.com"])).toBe(true);
    expect(hostMatchesAllowList("evil-internal.example.com", [".internal.example.com"])).toBe(false);
    expect(hostMatchesAllowList("internal.example.com", [])).toBe(false);
    expect(hostMatchesAllowList("INTERNAL.Example.COM", ["internal.example.com"])).toBe(true);
    expect(parseAllowedHosts(" localhost, 127.0.0.1 , , ::1 ")).toEqual(["localhost", "127.0.0.1", "::1"]);
  });
});

function rpcResponse(id: unknown, result: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: { "content-type": "application/json", ...headers }
  });
}
