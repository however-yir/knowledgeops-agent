"""Trusted Harness routes with explicit tenant-scoped confirmation records."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request

from knowledgeops_py.application.harness import CanonicalHarnessApplicationService


def sweep_expired_confirmations(store: Any, epoch_seconds: Callable[[], int]) -> None:
    """Drop used-up confirmation records so the map cannot grow without bound.

    Java parity (a373082 misc hardening): expired pending tokens used to live
    forever because execution only flips ``used``.
    """
    expired = [key for key, record in store.action_confirmations.items() if record["expiresAt"] <= epoch_seconds()]
    for key in expired:
        store.action_confirmations.pop(key, None)


def register_harness_routes(
    app: FastAPI,
    *,
    store: Any,
    harness_service: CanonicalHarnessApplicationService,
    memory_repository: Any,
    graph_repository: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    sha256_hex: Callable[[str], str],
    epoch_seconds: Callable[[], int],
    iso_at_epoch: Callable[[int], str],
    bounded: Callable[[int, int, int], int],
    execute_trusted_action: Callable[..., dict[str, Any]],
    harness_error: Callable[[str, str], dict[str, Any]],
) -> None:
    """Register Java-compatible trusted action preview and execution endpoints."""

    @app.get("/ai/harness/actions")
    def action_schema(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_AGENT_TRUSTED")),
    ) -> dict[str, Any]:
        legacy = is_legacy_request(request)
        schemas = [schema for schema in store.action_schemas if schema.get("contract") == ("legacy" if legacy else "canonical")]
        if legacy:
            schemas = [{key: value for key, value in schema.items() if key != "contract"} for schema in schemas]
        return ok(schemas, trace_id=ctx.trace_id)

    @app.post("/ai/harness/actions/preview")
    async def action_preview(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_AGENT_TRUSTED")),
    ) -> dict[str, Any]:
        payload = await request.json()
        action = str(payload.get("action", ""))
        legacy = is_legacy_request(request)
        if not legacy and not action.strip():
            raise HTTPException(status_code=400, detail="action is required")
        schema = next(
            (
                item
                for item in store.action_schemas
                if item["action"] == action and item.get("contract") == ("legacy" if legacy else "canonical")
            ),
            None,
        )
        if not schema:
            if legacy:
                raise HTTPException(status_code=404, detail="action not found")
            raise HTTPException(status_code=400, detail=f"unsupported action: {action}")
        action_input = payload.get("actionInput") or {}
        if not isinstance(action_input, dict):
            raise HTTPException(status_code=400, detail="actionInput must be an object")
        if legacy:
            missing = [key for key in schema["requiredKeys"] if key not in action_input]
            if missing:
                raise HTTPException(status_code=422, detail=f"missing action input: {', '.join(missing)}")
            token = secrets.token_urlsafe(32)
            expires_at = epoch_seconds() + 300
        else:
            if not schema["trustedOnly"]:
                raise HTTPException(status_code=400, detail=f"action does not require trusted runtime: {action}")
            token = f"ta-{secrets.token_hex(16)}"
            expires_at = epoch_seconds() + 600
        sweep_expired_confirmations(store, epoch_seconds)
        store.action_confirmations[sha256_hex(token)] = {
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "action": action,
            "actionInput": action_input,
            "expiresAt": expires_at,
            "used": False,
            "legacy": legacy,
            "schema": schema,
        }
        if legacy:
            return ok(
                {"confirmationToken": token, "action": action, "riskLevel": schema["riskLevel"], "expiresInSeconds": 300},
                trace_id=ctx.trace_id,
            )
        preview = harness_service.preview(ctx.tenant_id, action, action_input, schema)
        return ok(
            {"token": token, "action": action, "expiresAt": iso_at_epoch(expires_at), "preview": preview},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/harness/actions/execute/{token}")
    async def action_execute(
        token: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_AGENT_TRUSTED")),
    ) -> dict[str, Any]:
        legacy = is_legacy_request(request)
        confirmation = store.action_confirmations.get(sha256_hex(token))
        if not confirmation or confirmation["tenantId"] != ctx.tenant_id or confirmation["used"] or confirmation.get("legacy") != legacy:
            if legacy:
                raise HTTPException(status_code=404, detail="confirmation token not found")
            return ok(harness_error("trusted-action", "trusted action token not found"), trace_id=ctx.trace_id)
        if confirmation["expiresAt"] <= epoch_seconds():
            confirmation["used"] = True
            if legacy:
                raise HTTPException(status_code=404, detail="confirmation token not found")
            return ok(harness_error("trusted-action", "trusted action token expired"), trace_id=ctx.trace_id)
        confirmation["used"] = True
        if not legacy:
            return ok(
                harness_service.execute(
                    ctx.tenant_id,
                    confirmation["action"],
                    confirmation["actionInput"],
                    confirmation["schema"],
                ),
                trace_id=ctx.trace_id,
            )
        if memory_repository is not None and confirmation["action"] == "memory_save":
            action_input = confirmation["actionInput"]
            item = await memory_repository.create(
                ctx.tenant_id,
                ctx.principal,
                str(action_input["content"]),
                str(action_input.get("type") or "fact"),
                action_input.get("sessionId"),
            )
            observation = {"action": "memory_save", "status": "COMPLETED", "result": item}
        elif graph_repository is not None and confirmation["action"] == "graph_search":
            action_input = confirmation["actionInput"]
            observation = {
                "action": "graph_search",
                "status": "COMPLETED",
                "result": await graph_repository.list_entities(
                    ctx.tenant_id,
                    str(action_input["query"]),
                    limit=bounded(int(action_input.get("limit", 20)), 1, 100),
                ),
            }
        else:
            observation = execute_trusted_action(store, ctx, confirmation["action"], confirmation["actionInput"])
        return ok(observation, trace_id=ctx.trace_id)
