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
