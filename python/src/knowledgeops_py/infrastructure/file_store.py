from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocalFileStore:
    """Tenant-safe local storage adapter used until an S3 adapter is configured."""

    root: Path

    async def save(self, tenant_id: str, job_id: str, source_name: str, content: bytes) -> str:
        target = self._target(tenant_id, job_id, source_name)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)
        return str(target)

    async def read(self, tenant_id: str, file_path: str) -> bytes:
        target = self._checked_path(tenant_id, Path(file_path))
        return await asyncio.to_thread(target.read_bytes)

    async def delete(self, tenant_id: str, file_path: str) -> None:
        target = self._checked_path(tenant_id, Path(file_path))
        if target.exists():
            await asyncio.to_thread(target.unlink)

    def _target(self, tenant_id: str, job_id: str, source_name: str) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", source_name) or "upload.bin"
        return self._checked_path(tenant_id, self.root / tenant_id / f"{job_id}_{safe_name}")

    def _checked_path(self, tenant_id: str, candidate: Path) -> Path:
        tenant_root = (self.root / tenant_id).resolve()
        target = candidate.resolve()
        if target != tenant_root and tenant_root not in target.parents:
            raise ValueError("file path escapes tenant storage root")
        return target
