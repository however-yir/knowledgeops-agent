from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiEnvelope(BaseModel):
    ok: Literal[0, 1]
    msg: str
    data: Any = None
    traceId: str | None = None


class ErrorEnvelope(BaseModel):
    ok: Literal[0] = 0
    msg: str
    code: str
    traceId: str


class AuthTokenData(BaseModel):
    token: str
    refreshToken: str
    tokenType: str = "Bearer"
    expiresInSeconds: int
    tenantId: str
    principal: str
    roles: list[str]
    permissions: list[str]


class ApiKeyData(BaseModel):
    keyName: str
    tenantId: str
    role: str
    rawApiKey: str
    expiresAt: str


class ChatRequestDto(BaseModel):
    chatId: str
    prompt: str
    modelProfile: str = "balanced"


class UsageDto(BaseModel):
    inputTokens: int
    outputTokens: int
    totalTokens: int
    estimatedCostUsd: float


class AgentTraceDto(BaseModel):
    step: int
    thoughtSummary: str
    action: str
    actionInput: dict[str, Any] = Field(default_factory=dict)
    observation: Any = None


class ChatResponseDto(BaseModel):
    chatId: str | None = None
    answer: str
    model: str
    usage: UsageDto
    traceId: str
    trace: list[AgentTraceDto] = Field(default_factory=list)


class CitationDto(BaseModel):
    id: str
    source: str
    title: str
    chunkId: str
    snippet: str


class RetrievalStatsDto(BaseModel):
    keywordMatches: int
    vectorMatches: int
    hybridMatches: int
    evidenceAccepted: int
    refused: bool


class RagResponseDto(ChatResponseDto):
    citations: list[CitationDto] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    retrievalStats: RetrievalStatsDto


class IngestionJobDto(BaseModel):
    jobId: str
    chatId: str
    sourceName: str
    status: str
    attemptCount: int
    maxRetries: int
    queueBackend: str
    traceId: str
    createdAt: str
    updatedAt: str


class SessionDto(BaseModel):
    sessionId: str
    tenantId: str
    title: str
    chatId: str
    modelProfile: str
    updatedAt: str
    workspace: str | None = None
    branches: list[dict[str, Any]] = Field(default_factory=list)
    activeBranchId: str | None = None
    streaming: bool = True
    pinned: bool = False
    archived: bool = False
    messages: list[dict[str, Any]] = Field(default_factory=list)


class FeedbackRequestDto(BaseModel):
    chatId: str
    rating: int
    comment: str | None = None


class EvaluationRunRequestDto(BaseModel):
    datasetId: str | None = None
    modelProfile: str = "balanced"


class EvaluationDatasetCreateDto(BaseModel):
    name: str
    cases: list[dict[str, Any]]
    description: str | None = None


class CostSummaryDto(BaseModel):
    tenantId: str
    month: str
    monthCostUsd: float
    monthlyBudgetUsd: float
    hardLimitEnabled: bool
    monthRequestCount: int
    monthInputTokens: int
    monthOutputTokens: int
    todayCostUsd: float
    todayRequestCount: int
    budgetRemainingUsd: float
    budgetExceeded: bool


class BudgetUpdateDto(BaseModel):
    tenantId: str | None = None
    monthlyBudgetUsd: float
    hardLimitEnabled: bool | None = None


class AuditLogDto(BaseModel):
    tenantId: str
    principal: str
    method: str
    path: str
    status: int
    createdAt: str


class ChatEnvelope(ApiEnvelope):
    data: ChatResponseDto


class RagEnvelope(ApiEnvelope):
    data: RagResponseDto


class CostEnvelope(ApiEnvelope):
    data: CostSummaryDto


class AuditLogsEnvelope(ApiEnvelope):
    data: list[AuditLogDto]
