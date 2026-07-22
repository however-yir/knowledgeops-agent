from __future__ import annotations

import pytest

from knowledgeops_py.application.sessions import (
    SessionBranchValidationError,
    compare_session_branches,
    java_session_payload,
    merge_session_branches,
)


def test_session_branch_application_compares_merges_and_validates_inputs() -> None:
    session = java_session_payload(
        "session-a",
        {
            "title": "   ",
            "workspaceId": "   ",
            "branches": [
                {
                    "id": "source",
                    "messages": [
                        {"id": "same", "role": "user", "content": " common  message "},
                        {"id": "source-only", "role": "assistant", "content": "source only"},
                    ],
                },
                {
                    "id": "target",
                    "title": "Target",
                    "messages": [
                        {"id": "same", "role": "user", "content": "common message"},
                        {"id": "target-only", "role": "assistant", "content": "target only"},
                    ],
                },
            ],
        },
    )

    assert session["title"] == "新会话"
    assert session["workspace"] == "default"
    comparison = compare_session_branches(session, "source", "target")
    assert comparison["commonMessageCount"] == 1
    assert comparison["sourceOnlyPreview"] == ["source only"]

    merged, branch = merge_session_branches(session, "source", "target", None)
    assert branch["title"] == "Target · merge"
    assert [item["content"] for item in branch["messages"]] == ["common message", "target only", "source only"]
    assert merged["activeBranchId"] == branch["id"]

    with pytest.raises(SessionBranchValidationError, match="branch id is required"):
        compare_session_branches(session, "", "target")
