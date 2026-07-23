from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knowledgeops_py.application.harness import CanonicalHarnessApplicationService
from knowledgeops_py.config import Settings


@dataclass
class RecordingWorkspaceRuntime:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def execute(self, action: str, action_input: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((action, action_input))
        return {"status": "success", "action": action}


def test_canonical_harness_application_enforces_policy_and_redacts_previews() -> None:
    runtime = RecordingWorkspaceRuntime()
    service = CanonicalHarnessApplicationService(
        runtime,
        Settings(
            trusted_runtime_enabled=True,
            trusted_runtime_tenant_allowed_actions={"tenant-a": ("workspace_read_file",)},
        ),
    )
    schema = {
        "runtime": "workspace",
        "trustedOnly": True,
        "requiredFields": ["path"],
        "optionalFields": ["token"],
        "sensitiveFields": ["token"],
    }

    preview = service.preview("tenant-a", "workspace_read_file", {"path": "note.txt", "token": "secret"}, schema)
    assert preview["actionInput"] == {"path": "note.txt", "token": "[REDACTED]"}
    assert service.execute("tenant-a", "workspace_read_file", {"path": "note.txt", "token": "secret"}, schema) == {
        "status": "success",
        "action": "workspace_read_file",
    }
    assert runtime.calls == [("workspace_read_file", {"path": "note.txt", "token": "secret"})]
    assert service.execute("tenant-a", "workspace_list_files", {}, schema)["message"] == (
        "action is not allowed for tenant: workspace_list_files"
    )


def test_canonical_harness_application_covers_security_rejections_and_preview_bounds() -> None:
    runtime = RecordingWorkspaceRuntime()
    schema = {
        "runtime": "workspace",
        "trustedOnly": True,
        "requiredFields": ["path"],
        "optionalFields": ["content", "patch"],
        "sensitiveFields": [],
    }
    enabled = CanonicalHarnessApplicationService(runtime, Settings(trusted_runtime_enabled=True))

    assert (
        enabled.preview("tenant-a", "workspace_apply_patch", {"path": "note.txt", "content": "draft"}, schema)["action"]
        == "workspace_propose_patch"
    )
    assert (
        CanonicalHarnessApplicationService(
            runtime, Settings(trusted_runtime_enabled=True, trusted_runtime_disabled_actions=("workspace_read_file",))
        ).execute("tenant-a", "workspace_read_file", {"path": "note.txt"}, schema)["message"]
        == "action is disabled: workspace_read_file"
    )
    assert enabled.execute("tenant-a", "workspace_read_file", {"path": "note.txt"}, schema | {"trustedOnly": False})[
        "message"
    ] == ("action requires trusted runtime access: workspace_read_file")
    assert (
        CanonicalHarnessApplicationService(runtime, Settings()).execute(
            "tenant-a", "workspace_read_file", {"path": "note.txt"}, schema
        )["message"]
        == "trusted runtime is disabled"
    )
    assert (
        enabled.execute("tenant-a", "workspace_read_file", {}, schema)["message"] == "missing required field(s): path"
    )
    assert (
        enabled.execute("tenant-a", "workspace_propose_patch", {"path": "note.txt"}, schema)["message"]
        == "missing required field: content or patch"
    )
    assert (
        enabled.execute("tenant-a", "workspace_read_file", {"path": "note.txt", "extra": True}, schema)["message"]
        == "unknown field(s): extra"
    )
    assert (
        enabled.execute("tenant-a", "workspace_read_file", {"path": "note.txt"}, schema | {"runtime": "remote"})[
            "message"
        ]
        == "no runtime for action: workspace_read_file"
    )

    preview = enabled.preview(
        "tenant-a",
        "workspace_read_file",
        {
            "password": "hidden",
            "long": "x" * 601,
            "nested": {str(index): index for index in range(61)},
            "items": list(range(31)),
            "number": 1,
        },
        schema,
    )["actionInput"]
    assert preview["password"] == "[REDACTED]"
    assert preview["long"] == "x" * 600 + "...[truncated]"
    assert preview["nested"]["_truncated"] is True and len(preview["nested"]) == 61
    assert preview["items"][-1] == {"_truncated": True} and preview["number"] == 1
