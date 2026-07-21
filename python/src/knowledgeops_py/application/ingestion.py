from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pypdf import PdfReader

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.file_store import LocalFileStore
from knowledgeops_py.infrastructure.ingestion_repository import PersistedIngestionJob, SqlAlchemyIngestionRepository
from knowledgeops_py.infrastructure.models import IngestionJobRecord


@dataclass(slots=True)
class IngestionApplicationService:
    repository: SqlAlchemyIngestionRepository
    files: LocalFileStore
    queue_backend: str
    max_retries: int = 3
    retry_delay_seconds: int = 10

    async def submit(self, context: TenantContext, chat_id: str, source_name: str, content: bytes) -> PersistedIngestionJob:
        idempotency_key = hashlib.sha256(f"{context.tenant_id}|{chat_id}|".encode() + content).hexdigest()
        existing = await self.repository.find_by_idempotency(context.tenant_id, idempotency_key)
        if existing is not None:
            return existing
        job_id = f"job_{uuid4().hex[:16]}"
        file_path = await self.files.save(context.tenant_id, job_id, source_name, content)
        try:
            return await self.repository.create(
                IngestionJobRecord(
                    job_id=job_id,
                    tenant_id=context.tenant_id,
                    chat_id=chat_id,
                    source_type="PDF" if source_name.lower().endswith(".pdf") else "FILE",
                    source_name=source_name,
                    file_path=file_path,
                    status="QUEUED",
                    idempotency_key=idempotency_key,
                    max_retries=self.max_retries,
                    trace_id=context.trace_id,
                    queue_backend=self.queue_backend,
                    payload={},
                )
            )
        except Exception:
            await self.files.delete(context.tenant_id, file_path)
            raise

    async def process(self, job_id: str) -> PersistedIngestionJob | None:
        job = await self.repository.claim(job_id)
        if job is None:
            return None
        try:
            if not job.file_path:
                raise RuntimeError("ingestion file path is missing")
            content = await self.files.read(job.tenant_id, job.file_path)
            chunks = self._chunks(job, extract_text(content))
            await self.repository.complete(job.job_id, chunks)
            return await self.repository.get(job.tenant_id, job.job_id)
        except Exception as exc:
            return await self.repository.fail(job.job_id, str(exc), self.retry_delay_seconds)

    async def process_ready(self, tenant_id: str | None = None, limit: int = 100) -> int:
        processed = 0
        for job_id in await self.repository.ready_job_ids(tenant_id, limit):
            if await self.process(job_id) is not None:
                processed += 1
        return processed

    def _chunks(self, job: PersistedIngestionJob, text: str) -> list[dict[str, Any]]:
        parts = split_text(text)
        return [
            {
                "chunk_id": f"chunk_{uuid4().hex[:16]}",
                "job_id": job.job_id,
                "tenant_id": job.tenant_id,
                "chat_id": job.chat_id,
                "source_name": job.source_name,
                "chunk_index": index,
                "content": part,
                "token_count": len(tokenize(part)),
                "embedding": None,
            }
            for index, part in enumerate(parts)
        ]


def extract_text(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages).strip()
    return content.decode("utf-8", errors="strict").strip()


def split_text(text: str, chunk_size: int = 700) -> list[str]:
    normalized = text.strip()
    if not normalized:
        raise ValueError("uploaded document contains no extractable text")
    return [normalized[index : index + chunk_size] for index in range(0, len(normalized), chunk_size)]


def tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", value.lower()) if token]
