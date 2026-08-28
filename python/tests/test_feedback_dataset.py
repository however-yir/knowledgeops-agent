"""Feedback dataset writer tests (Java parity 06c7cb0: cap and rotate)."""

from __future__ import annotations

import json

from knowledgeops_py.infrastructure.feedback_dataset import FeedbackDatasetWriter


def test_appends_jsonl_records(tmp_path) -> None:
    writer = FeedbackDatasetWriter(tmp_path / "datasets" / "feedback.jsonl")

    writer.append({"chatId": "c1", "rating": 1, "tenantId": "tenant-a"})
    writer.append({"chatId": "c2", "rating": -1, "tenantId": "tenant-b"})

    lines = (tmp_path / "datasets" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["chatId"] == "c1"
    assert json.loads(lines[1])["tenantId"] == "tenant-b"


def test_rotates_when_cap_reached(tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    writer = FeedbackDatasetWriter(path, max_bytes=10)

    writer.append({"chatId": "first-record-that-is-well-over-ten-bytes"})
    writer.append({"chatId": "second"})

    rotated = list(tmp_path.glob("feedback-*.jsonl"))
    assert len(rotated) == 1
    assert json.loads(rotated[0].read_text(encoding="utf-8"))["chatId"] == "first-record-that-is-well-over-ten-bytes"
    assert json.loads(path.read_text(encoding="utf-8"))["chatId"] == "second"


def test_zero_cap_disables_rotation(tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    writer = FeedbackDatasetWriter(path, max_bytes=0)

    writer.append({"chatId": "one"})
    writer.append({"chatId": "two"})

    rotated = list(tmp_path.glob("feedback-*.jsonl"))
    assert rotated == []
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
