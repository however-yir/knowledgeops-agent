"""Append-only JSONL feedback dataset with size-cap rotation.

Java parity (06c7cb0): a single tenant — or an attacker with a leaked
credential — must not be able to exhaust the disk by repeatedly submitting
feedback. When the active dataset file is at or above the configured cap,
the writer rotates it to a timestamped sibling instead of appending further.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MAX_DATASET_BYTES = 50 * 1024 * 1024


@dataclass(slots=True)
class FeedbackDatasetWriter:
    path: Path
    max_bytes: int = DEFAULT_MAX_DATASET_BYTES

    def append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.max_bytes > 0 and self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            rotated = self.path.with_name(f"{self.path.stem}-{timestamp}{self.path.suffix}")
            self.path.rename(rotated)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(record), ensure_ascii=False, default=str) + "\n")
