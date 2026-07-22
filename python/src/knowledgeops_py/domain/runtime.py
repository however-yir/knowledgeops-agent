"""Request-scoped identity and the in-memory demo runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestContext:
    trace_id: str
    tenant_id: str
    principal: str
    roles: list[str]
    permissions: list[str]
    auth_source: str


@dataclass
class PlatformStore:
    api_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    refresh_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    rate_limits: dict[str, list[float]] = field(default_factory=dict)
    audit_logs: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    queue: list[str] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    eval_datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    eval_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    budgets: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    action_schemas: list[dict[str, Any]] = field(default_factory=list)
    oidc_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    oidc_exchange_codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    revoked_refresh_tokens: set[str] = field(default_factory=set)
    workflow_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    research_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    memories: dict[str, dict[str, Any]] = field(default_factory=dict)
    graph_entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    graph_facts: list[dict[str, Any]] = field(default_factory=list)
    action_confirmations: dict[str, dict[str, Any]] = field(default_factory=dict)
