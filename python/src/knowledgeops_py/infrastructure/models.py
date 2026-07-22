from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantScopedRecord:
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ApiKeyRecord(Base, TenantScopedRecord):
    __tablename__ = "py_api_keys"
    key_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    key_name: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(255))
    rotated_from_key_hash: Mapped[str | None] = mapped_column(String(128))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class RefreshTokenRecord(Base, TenantScopedRecord):
    __tablename__ = "py_refresh_tokens"
    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    principal: Mapped[str] = mapped_column(String(255), index=True)
    roles: Mapped[list[str]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJobRecord(Base, TenantScopedRecord):
    __tablename__ = "py_ingestion_jobs"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="FILE")
    source_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    queue_backend: Mapped[str] = mapped_column(String(32), default="db_polling")
    error_message: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class IngestionChunkRecord(Base, TenantScopedRecord):
    __tablename__ = "py_ingestion_chunks"
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    source_name: Mapped[str] = mapped_column(String(512))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)


class SessionRecord(Base, TenantScopedRecord):
    __tablename__ = "py_agent_sessions"
    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLogRecord(Base, TenantScopedRecord):
    __tablename__ = "py_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    principal: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[int] = mapped_column(Integer)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON)


class TenantBudgetRecord(Base, TenantScopedRecord):
    __tablename__ = "py_tenant_budgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monthly_budget_usd: Mapped[float] = mapped_column(Float)
    hard_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MemoryRecord(Base, TenantScopedRecord):
    __tablename__ = "py_memory_items"
    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal: Mapped[str] = mapped_column(String(255), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True)
    type: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)


class GraphEntityRecord(Base, TenantScopedRecord):
    __tablename__ = "py_graph_entities"
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    type: Mapped[str] = mapped_column(String(128))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkflowTaskRecord(Base, TenantScopedRecord):
    __tablename__ = "py_workflow_tasks"
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowStepRecord(Base, TenantScopedRecord):
    __tablename__ = "py_workflow_steps"
    step_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), default="planner")
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    thought: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(String(64))
    action_input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_profile: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowEventRecord(Base, TenantScopedRecord):
    __tablename__ = "py_workflow_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    step_id: Mapped[str | None] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EvaluationRunRecord(Base, TenantScopedRecord):
    __tablename__ = "py_evaluation_runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    results: Mapped[dict[str, Any]] = mapped_column(JSON)
