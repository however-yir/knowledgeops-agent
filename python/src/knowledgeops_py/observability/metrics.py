"""In-memory development metrics and Prometheus exposition rendering."""

from __future__ import annotations

from knowledgeops_py.domain.runtime import PlatformStore


def prometheus_text(store: PlatformStore) -> str:
    lines = ["# HELP knowledgeops_python_up Python service liveness", "# TYPE knowledgeops_python_up gauge", "knowledgeops_python_up 1"]
    for name, value in sorted(store.metrics.items()):
        lines.extend([f"# TYPE {name} counter", f"{name} {value:g}"])
    return "\n".join(lines) + "\n"


def metric_inc(store: PlatformStore, name: str, amount: float = 1.0) -> None:
    store.metrics[name] = store.metrics.get(name, 0.0) + amount
