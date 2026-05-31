import { createHash } from "node:crypto";

import { Injectable } from "@nestjs/common";

import { nowIso } from "../common/ids.js";
import { normalizeTenant } from "../common/tenant.js";
import { env } from "../config/env.js";
import { PlatformStore } from "./platform.store.js";

export interface ModelRouteDecision {
  profile: string;
  model: string;
  costTier: "low" | "balanced" | "high";
  fallbackApplied: boolean;
  reason: string;
  experimentKey?: string;
  experimentVariant?: string;
  experimentBucket?: number;
}

@Injectable()
export class ModelRouterService {
  constructor(private readonly store: PlatformStore) {}

  resolve(requestedProfile: string | undefined, endpoint: string, tenantId: string | undefined, subjectKey = ""): ModelRouteDecision {
    const tenant = normalizeTenant(tenantId);
    const initial = normalizeProfile(requestedProfile || env.APP_MODEL_DEFAULT_PROFILE);
    const experiment = this.applyExperiment(initial, endpoint, tenant, subjectKey);
    const profile = experiment.routedProfile || "balanced";
    const decision = this.resolveProfile(profile, initial);
    const routed = {
      ...decision,
      experimentKey: experiment.experimentKey,
      experimentVariant: experiment.variant,
      experimentBucket: experiment.bucket
    };
    if (routed.experimentKey) {
      this.store.modelExposures.push({
        tenantId: tenant,
        experimentKey: routed.experimentKey,
        subjectKey: subjectKey || "na",
        endpoint,
        bucket: routed.experimentBucket ?? -1,
        variant: routed.experimentVariant || "unknown",
        routedProfile: routed.profile,
        createdAt: nowIso()
      });
      this.store.persist();
    }
    return routed;
  }

  private resolveProfile(profile: string, requested: string): ModelRouteDecision {
    if (profile === "economy" || profile === "cost" || profile === "cost_first") {
      return {
        profile: "economy",
        model: env.APP_MODEL_ECONOMY,
        costTier: "low",
        fallbackApplied: requested !== "economy",
        reason: requested !== "economy" ? "fallback_chain" : "profile_match"
      };
    }
    if (profile === "quality" || profile === "quality_first") {
      return {
        profile: "quality",
        model: env.APP_MODEL_QUALITY,
        costTier: "high",
        fallbackApplied: requested !== "quality",
        reason: requested !== "quality" ? "fallback_chain" : "profile_match"
      };
    }
    return {
      profile: "balanced",
      model: env.APP_MODEL_BALANCED,
      costTier: "balanced",
      fallbackApplied: requested !== "balanced" && requested !== "ab_auto",
      reason: requested === "balanced" || requested === "ab_auto" ? "profile_match" : "default_model_fallback"
    };
  }

  private applyExperiment(profile: string, endpoint: string, tenantId: string, subjectKey: string) {
    if (profile === "quality_first") {
      return { routedProfile: "quality", experimentKey: "manual_quality_first", variant: "quality", bucket: 100 };
    }
    if (profile === "cost_first") {
      return { routedProfile: "economy", experimentKey: "manual_cost_first", variant: "cost", bucket: 0 };
    }
    if (profile !== "ab_auto") {
      return { routedProfile: profile, experimentKey: undefined, variant: undefined, bucket: undefined };
    }
    const bucket = stableBucket(`${tenantId}|${endpoint}|${subjectKey || "na"}`);
    const quality = bucket < env.APP_MODEL_AB_QUALITY_PERCENT;
    return {
      routedProfile: quality ? "quality" : "economy",
      experimentKey: "quality_vs_cost",
      variant: quality ? "quality" : "cost",
      bucket
    };
  }
}

function normalizeProfile(profile: string): string {
  return profile.trim().toLowerCase().replace(/-/g, "_") || "balanced";
}

function stableBucket(value: string): number {
  return createHash("sha256").update(value).digest()[0] % 100;
}
