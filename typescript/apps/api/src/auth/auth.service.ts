import { randomBytes } from "node:crypto";

import { Injectable } from "@nestjs/common";
import jwt from "jsonwebtoken";
import type { ApiKeyIssueResponse, AuthTokenResponse } from "@knowledgeops/shared";

import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { PlatformStore, sha256Hex } from "../platform/platform.store.js";

const ROLE_PERMISSIONS: Record<string, string[]> = {
  ADMIN: ["ROLE_ADMIN", "PERM_AUTH_KEY_MANAGE", "PERM_CHAT_WRITE", "PERM_INGESTION_WRITE", "PERM_AGENT_TRUSTED", "PERM_EVAL_WRITE"],
  OPS: ["ROLE_OPS", "PERM_METRICS_READ", "PERM_AUDIT_READ", "PERM_EVAL_READ"],
  USER: ["ROLE_USER", "PERM_CHAT_WRITE", "PERM_INGESTION_WRITE", "PERM_RAG_READ"]
};

@Injectable()
export class AuthService {
  constructor(private readonly store: PlatformStore) {}

  exchangeApiKey(apiKey: string | undefined, tenantHeader: string | undefined): AuthTokenResponse {
    if (!apiKey) {
      return { ok: 0, msg: "invalid api key" };
    }
    const record = this.store.apiKeys.get(sha256Hex(apiKey));
    if (!record || !record.enabled) {
      return { ok: 0, msg: "invalid api key" };
    }
    const tenantId = normalizeTenant(record.tenantId);
    if (tenantHeader && normalizeTenant(tenantHeader) !== tenantId) {
      return { ok: 0, msg: "tenant mismatch for api key" };
    }
    return this.issueTokens(record.keyName, [record.roleName], tenantId);
  }

  refresh(refreshToken: string | undefined): AuthTokenResponse {
    if (!refreshToken) {
      return { ok: 0, msg: "invalid refresh token" };
    }
    const record = this.store.refreshTokens.get(refreshToken);
    if (!record || Date.parse(record.expiresAt) <= Date.now()) {
      return { ok: 0, msg: "invalid refresh token" };
    }
    this.store.refreshTokens.delete(refreshToken);
    return this.issueTokens(record.principal, record.roles, record.tenantId);
  }

  issueApiKey(keyName: string, roleName: string, tenantId?: string): ApiKeyIssueResponse {
    const rawApiKey = `koa_${randomBytes(24).toString("hex")}`;
    const normalizedTenant = normalizeTenant(tenantId);
    this.store.apiKeys.set(sha256Hex(rawApiKey), {
      keyHash: sha256Hex(rawApiKey),
      keyName,
      roleName: roleName || "USER",
      tenantId: normalizedTenant,
      enabled: true,
      expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()
    });
    return {
      ok: 1,
      msg: "ok",
      keyName,
      tenantId: normalizedTenant,
      rawApiKey,
      expiresAt: this.store.apiKeys.get(sha256Hex(rawApiKey))?.expiresAt
    };
  }

  rotateApiKey(keyName: string, roleName = "USER", tenantId?: string): ApiKeyIssueResponse {
    for (const record of this.store.apiKeys.values()) {
      if (record.keyName === keyName && record.tenantId === normalizeTenant(tenantId)) {
        record.enabled = false;
      }
    }
    return {
      ...this.issueApiKey(keyName, roleName, tenantId),
      msg: "rotated"
    };
  }

  revokeApiKey(keyName: string, tenantId?: string): ApiKeyIssueResponse {
    const normalizedTenant = normalizeTenant(tenantId);
    for (const record of this.store.apiKeys.values()) {
      if (record.keyName === keyName && record.tenantId === normalizedTenant) {
        record.enabled = false;
      }
    }
    return { ok: 1, msg: "revoked", keyName, tenantId: normalizedTenant };
  }

  private issueTokens(principal: string, roles: string[], tenantId: string): AuthTokenResponse {
    const permissions = [...new Set(roles.flatMap((role) => ROLE_PERMISSIONS[role] ?? []))];
    const token = jwt.sign({ sub: principal, roles, permissions, tenantId }, env.APP_JWT_SECRET, {
      expiresIn: `${env.APP_JWT_EXPIRE_MINUTES}m`
    });
    const refreshToken = newId("refresh");
    const refreshExpiresAt = new Date(Date.now() + env.APP_REFRESH_EXPIRE_DAYS * 24 * 60 * 60 * 1000).toISOString();
    this.store.refreshTokens.set(refreshToken, {
      token: refreshToken,
      principal,
      roles,
      tenantId,
      expiresAt: refreshExpiresAt
    });
    return {
      ok: 1,
      msg: "ok",
      token,
      refreshToken,
      tenantId,
      expiresInSeconds: env.APP_JWT_EXPIRE_MINUTES * 60,
      refreshWillExpireSoon: Date.parse(refreshExpiresAt) < Date.now() + 2 * 24 * 60 * 60 * 1000
    };
  }
}
