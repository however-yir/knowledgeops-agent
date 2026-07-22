import { afterEach, describe, expect, it, vi } from "vitest";

import { env } from "../config/env.js";
import { McpClient } from "./mcp.client.js";

const originalConfig = env.APP_MCP_SERVERS_JSON;

afterEach(() => {
  env.APP_MCP_SERVERS_JSON = originalConfig;
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
});

function rpcResponse(id: unknown, result: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: { "content-type": "application/json", ...headers }
  });
}
