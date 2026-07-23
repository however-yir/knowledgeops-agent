from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knowledgeops_py.config import Settings
from knowledgeops_py.domain.ports import TrustedWorkspaceRuntime


@dataclass(slots=True)
class CanonicalHarnessApplicationService:
    runtime: TrustedWorkspaceRuntime
    settings: Settings

    def preview(self, tenant_id: str, action: str, action_input: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        if action == "workspace_apply_patch":
            return self.execute(tenant_id, "workspace_propose_patch", action_input, schema)
        return canonical_harness_preview(action, action_input, schema)

    def execute(self, tenant_id: str, action: str, action_input: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        if action in self.settings.trusted_runtime_disabled_actions:
            return harness_error("policy", f"action is disabled: {action}")
        allowed = self.settings.trusted_runtime_tenant_allowed_actions.get(tenant_id, ())
        if allowed and action not in allowed:
            return harness_error("policy", f"action is not allowed for tenant: {action}")
        if not schema.get("trustedOnly"):
            return harness_error("policy", f"action requires trusted runtime access: {action}")
        if not self.settings.trusted_runtime_enabled:
            return harness_error("policy", "trusted runtime is disabled")
        missing = [field for field in schema["requiredFields"] if not harness_has_value(action_input.get(field))]
        if missing:
            return harness_error("policy", f"missing required field(s): {', '.join(missing)}")
        if action in {"workspace_propose_patch", "workspace_apply_patch"} and not (
            harness_has_value(action_input.get("content")) or harness_has_value(action_input.get("patch"))
        ):
            return harness_error("policy", "missing required field: content or patch")
        known = {*schema["requiredFields"], *schema["optionalFields"]}
        unknown = [field for field in action_input if field not in known]
        if unknown:
            return harness_error("policy", f"unknown field(s): {', '.join(unknown)}")
        if schema["runtime"] == "workspace":
            return self.runtime.execute(action, action_input)
        return harness_error("runtime", f"no runtime for action: {action}")


def canonical_harness_preview(action: str, action_input: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending_confirmation",
        "source": schema["runtime"],
        "action": action,
        "actionInput": sanitize_harness_action_input(action_input, schema),
    }


def sanitize_harness_action_input(action_input: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    sensitive = set(schema["sensitiveFields"])
    keywords = ("password", "secret", "token", "apikey", "api_key", "contactinfo", "authorization")
    return {
        key: "[REDACTED]"
        if key in sensitive or any(keyword in key.lower() for keyword in keywords)
        else limit_harness_value(value)
        for key, value in action_input.items()
    }


def limit_harness_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 600 else f"{value[:600]}...[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {str(key): limit_harness_value(item) for key, item in list(value.items())[:60]}
        if len(value) > 60:
            result["_truncated"] = True
        return result
    if isinstance(value, list):
        result_list: list[Any] = [limit_harness_value(item) for item in value[:30]]
        if len(value) > 30:
            result_list.append({"_truncated": True})
        return result_list
    return value


def harness_has_value(value: Any) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None


def harness_error(source: str, message: str) -> dict[str, Any]:
    return {"status": "error", "source": source, "latencyMs": 0, "message": message}
