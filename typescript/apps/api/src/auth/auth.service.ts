import { randomBytes } from "node:crypto";

import { Injectable } from "@nestjs/common";
import jwt from "jsonwebtoken";
import type { ApiKeyIssueResponse, AuthTokenResponse } from "@knowledgeops/shared";

import { newId, nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { PlatformStore, sha256Hex } from "../platform/platform.store.js";

const ROLE_PERMISSIONS: Record<string, string[]> = {
  ADMIN: [
    "ROLE_ADMIN",
    "PERM_AUTH_KEY_MANAGE",
    "PERM_CHAT_READ",
    "PERM_CHAT_WRITE",
    "PERM_INGESTION_READ",
    "PERM_INGESTION_WRITE",
    "PERM_RAG_READ",
    "PERM_METRICS_READ",
    "PERM_AUDIT_READ",
    "PERM_SESSION_READ",
    "PERM_SESSION_WRITE",
    "PERM_FEEDBACK_WRITE",
    "PERM_COST_READ",
    "PERM_COST_WRITE",
    "PERM_AGENT_TRUSTED",
    "PERM_EVAL_READ",
    "PERM_EVAL_WRITE"
  ],
  OPS: [
    "ROLE_OPS",
    "PERM_INGESTION_READ",
    "PERM_METRICS_READ",
    "PERM_AUDIT_READ",
    "PERM_SESSION_READ",
    "PERM_COST_READ",
    "PERM_EVAL_READ"
  ],
  USER: [
    "ROLE_USER",
    "PERM_CHAT_READ",
    "PERM_CHAT_WRITE",
    "PERM_INGESTION_READ",
    "PERM_INGESTION_WRITE",
    "PERM_RAG_READ",
    "PERM_SESSION_READ",
    "PERM_SESSION_WRITE",
    "PERM_FEEDBACK_WRITE",
    "PERM_COST_READ",
    "PERM_EVAL_READ",
    "PERM_EVAL_WRITE"
  ]
};

@Injectable()
export class AuthService {
  constructor(private readonly store: PlatformStore) {}

  authenticateApiKey(apiKey: string | undefined, tenantHeader?: string) {
    if (!apiKey) {
      return undefined;
    }
    const record = this.store.apiKeys.get(sha256Hex(apiKey.trim()));
    if (!record || !record.enabled || record.revokedAt || (record.expiresAt && Date.parse(record.expiresAt) <= Date.now())) {
      return undefined;
    }
    const tenantId = normalizeTenant(record.tenantId);
    if (tenantHeader && normalizeTenant(tenantHeader) !== tenantId) {
      return undefined;
    }
    record.lastUsedAt = nowIso();
    record.updatedAt = nowIso();
    this.store.persist();
    return {
      principal: record.keyName,
      roles: [record.roleName],
      permissions: this.permissionsForRoles([record.roleName]),
      tenantId,
      source: "api_key" as const
    };
  }

  parseJwt(token: string | undefined) {
    if (!token) {
      return undefined;
    }
    try {
      const decoded = jwt.verify(token, env.APP_JWT_SECRET) as {
        sub?: string;
        roles?: string[];
        permissions?: string[];
        tenant_id?: string;
        tenantId?: string;
      };
      if (!decoded.sub) {
        return undefined;
      }
      const roles = decoded.roles?.length ? decoded.roles : ["USER"];
      return {
        principal: decoded.sub,
        roles,
        permissions: decoded.permissions ?? this.permissionsForRoles(roles),
        tenantId: normalizeTenant(decoded.tenant_id ?? decoded.tenantId),
        source: "jwt" as const
      };
    } catch {
      return undefined;
    }
  }

  exchangeApiKey(apiKey: string | undefined, tenantHeader: string | undefined): AuthTokenResponse {
    const identity = this.authenticateApiKey(apiKey, tenantHeader);
    if (!identity) {
      return { ok: 0, msg: apiKey ? "tenant mismatch for api key" : "invalid api key" };
    }
    return this.issueTokens(identity.principal, identity.roles, identity.tenantId);
  }

  refresh(refreshToken: string | undefined): AuthTokenResponse {
    if (!refreshToken) {
      return { ok: 0, msg: "invalid refresh token" };
    }
    const tokenHash = sha256Hex(refreshToken);
    const record = this.store.refreshTokens.get(tokenHash);
    if (!record || record.revokedAt || Date.parse(record.expiresAt) <= Date.now()) {
      return { ok: 0, msg: "invalid refresh token" };
    }
    this.store.refreshTokens.delete(tokenHash);
    this.store.persist();
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
      expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      createdAt: nowIso(),
      updatedAt: nowIso()
    });
    this.store.persist();
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
    let rotatedFromId: string | undefined;
    for (const record of this.store.apiKeys.values()) {
      if (record.keyName === keyName && record.tenantId === normalizeTenant(tenantId)) {
        record.enabled = false;
        record.revokedAt = nowIso();
        record.revokedReason = "rotated";
        record.updatedAt = nowIso();
        rotatedFromId = record.keyHash;
      }
    }
    const issued = this.issueApiKey(keyName, roleName, tenantId);
    if (issued.rawApiKey && rotatedFromId) {
      const inserted = this.store.apiKeys.get(sha256Hex(issued.rawApiKey));
      if (inserted) {
        inserted.rotatedFromId = rotatedFromId;
        this.store.persist();
      }
    }
    return {
      ...issued,
      msg: "rotated"
    };
  }

  revokeApiKey(keyName: string, tenantId?: string): ApiKeyIssueResponse {
    const normalizedTenant = normalizeTenant(tenantId);
    for (const record of this.store.apiKeys.values()) {
      if (record.keyName === keyName && record.tenantId === normalizedTenant) {
        record.enabled = false;
        record.revokedAt = nowIso();
        record.revokedReason = "manual revoke";
        record.updatedAt = nowIso();
      }
    }
    this.store.persist();
    return { ok: 1, msg: "revoked", keyName, tenantId: normalizedTenant };
  }

  private issueTokens(principal: string, roles: string[], tenantId: string): AuthTokenResponse {
    const permissions = [...new Set(roles.flatMap((role) => ROLE_PERMISSIONS[role] ?? []))];
    const token = jwt.sign({ sub: principal, roles, permissions, tenant_id: tenantId }, env.APP_JWT_SECRET, {
      expiresIn: `${env.APP_JWT_EXPIRE_MINUTES}m`
    });
    const refreshToken = newId("refresh");
    const tokenHash = sha256Hex(refreshToken);
    const refreshExpiresAt = new Date(Date.now() + env.APP_REFRESH_EXPIRE_DAYS * 24 * 60 * 60 * 1000).toISOString();
    this.store.refreshTokens.set(tokenHash, {
      tokenHash,
      principal,
      roles,
      tenantId,
      expiresAt: refreshExpiresAt,
      createdAt: nowIso()
    });
    this.store.persist();
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

  private permissionsForRoles(roles: string[]): string[] {
    return [...new Set(roles.flatMap((role) => ROLE_PERMISSIONS[role] ?? []))];
  }
}
