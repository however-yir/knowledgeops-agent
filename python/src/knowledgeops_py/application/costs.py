"""Cost and token-accounting functions for application services."""

from __future__ import annotations

from datetime import date

from ..domain.runtime import PlatformStore
from ..dto import CostSummaryDto, UsageDto


def cost_summary_data(store: PlatformStore, tenant_id: str) -> CostSummaryDto:
    usage = store.usage.get(tenant_id, {"monthCostUsd": 0.0, "requestCount": 0, "inputTokens": 0, "outputTokens": 0})
    budget = store.budgets.get(tenant_id, {"monthlyBudgetUsd": 25.0, "hardLimitEnabled": False})
    month_cost = float(usage.get("monthCostUsd", 0.0))
    monthly_budget = float(budget.get("monthlyBudgetUsd", 25.0))
    request_count = int(usage.get("requestCount", 0))
    input_tokens = int(usage.get("inputTokens", 0))
    output_tokens = int(usage.get("outputTokens", 0))
    return CostSummaryDto(
        tenantId=tenant_id,
        month=date.today().strftime("%Y-%m"),
        monthCostUsd=_round4(month_cost),
        monthlyBudgetUsd=_round4(monthly_budget),
        hardLimitEnabled=bool(budget.get("hardLimitEnabled", False)),
        monthRequestCount=request_count,
        monthInputTokens=input_tokens,
        monthOutputTokens=output_tokens,
        todayCostUsd=_round4(month_cost),
        todayRequestCount=request_count,
        budgetRemainingUsd=_round4(max(0.0, monthly_budget - month_cost)),
        budgetExceeded=month_cost > monthly_budget,
    )


def record_provider_usage(store: PlatformStore, tenant_id: str, input_tokens: int, output_tokens: int) -> UsageDto:
    cost = _round4(input_tokens * 0.000001 + output_tokens * 0.000002)
    usage = store.usage.setdefault(tenant_id, {"monthCostUsd": 0.0, "requestCount": 0, "inputTokens": 0, "outputTokens": 0})
    usage["monthCostUsd"] = _round4(float(usage["monthCostUsd"]) + cost)
    usage["requestCount"] += 1
    usage["inputTokens"] = int(usage.get("inputTokens", 0)) + input_tokens
    usage["outputTokens"] = int(usage.get("outputTokens", 0)) + output_tokens
    return UsageDto(inputTokens=input_tokens, outputTokens=output_tokens, totalTokens=input_tokens + output_tokens, estimatedCostUsd=cost)


def _round4(value: float) -> float:
    return round(value, 4)
