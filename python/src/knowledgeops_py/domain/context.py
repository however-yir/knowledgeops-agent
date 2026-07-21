from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Authentication-derived scope used by every application operation."""

    trace_id: str
    tenant_id: str
    principal: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    auth_source: str

    def has(self, permission: str) -> bool:
        return permission in self.permissions
