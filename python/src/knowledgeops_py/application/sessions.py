from __future__ import annotations

import hashlib
import re
import secrets
import time
from typing import Any


class SessionBranchValidationError(ValueError):
    """Raised when a requested session branch cannot be used."""


def java_session_payload(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = java_default_text(payload.get("workspaceId"), "default")
    branches = payload.get("branches") if isinstance(payload.get("branches"), list) else []
    active_branch_id = payload.get("activeBranchId")
    if not isinstance(active_branch_id, str) or not active_branch_id.strip():
        active_branch_id = branches[0].get("id") if branches and isinstance(branches[0], dict) else None
    return {
        "sessionId": session_id,
        "chatId": session_id,
        "title": java_default_text(payload.get("title"), "新会话"),
        "modelProfile": java_default_text(payload.get("modelProfile"), "balanced"),
        "streaming": payload["streaming"] if isinstance(payload.get("streaming"), bool) else True,
        "pinned": bool(payload.get("pinned", False)),
        "archived": bool(payload.get("archived", False)),
        "workspace": workspace_id,
        "activeBranchId": active_branch_id,
        "branches": branches,
        "messages": [],
    }


def java_default_text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def compare_session_branches(
    session_data: dict[str, Any], source_branch_id: Any, target_branch_id: Any
) -> dict[str, Any]:
    source = find_session_branch(session_data, source_branch_id)
    target = find_session_branch(session_data, target_branch_id)
    source_messages = branch_messages(source)
    target_messages = branch_messages(target)
    source_fingerprints = {session_message_fingerprint(item) for item in source_messages}
    target_fingerprints = {session_message_fingerprint(item) for item in target_messages}
    common = source_fingerprints & target_fingerprints
    source_only = source_fingerprints - target_fingerprints
    target_only = target_fingerprints - source_fingerprints
    return {
        "sourceBranchId": source_branch_id,
        "targetBranchId": target_branch_id,
        "sourceMessageCount": len(source_messages),
        "targetMessageCount": len(target_messages),
        "commonMessageCount": len(common),
        "sourceOnlyCount": len(source_only),
        "targetOnlyCount": len(target_only),
        "sourceOnlyPreview": branch_preview(source_messages, source_only),
        "targetOnlyPreview": branch_preview(target_messages, target_only),
    }


def merge_session_branches(
    session_data: dict[str, Any], source_branch_id: Any, target_branch_id: Any, title: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = find_session_branch(session_data, source_branch_id)
    target = find_session_branch(session_data, target_branch_id)
    target_messages = [copy_session_message(message) for message in branch_messages(target)]
    source_messages = [copy_session_message(message) for message in branch_messages(source)]
    target_fingerprints = {session_message_fingerprint(message) for message in target_messages}
    existing_ids = {str(message["id"]) for message in target_messages if message.get("id")}
    for message in source_messages:
        fingerprint = session_message_fingerprint(message)
        if fingerprint in target_fingerprints:
            continue
        ensure_unique_session_message_id(message, existing_ids)
        target_messages.append(message)
        target_fingerprints.add(fingerprint)
    updated_at = current_epoch_millis()
    branch_id = f"branch-merge-{updated_at}-{secrets.randbelow(100000)}"
    branch_title = str(title).strip() if isinstance(title, str) and title.strip() else f"{target.get('title') or '分支'} · merge"
    merged_branch = {
        "id": branch_id,
        "title": branch_title,
        "parentBranchId": target.get("id"),
        "parentMessageId": target.get("parentMessageId"),
        "updatedAt": updated_at,
        "messages": target_messages,
        "traceSteps": target.get("traceSteps"),
    }
    branches = [merged_branch, *[item for item in session_data.get("branches", []) if isinstance(item, dict)]]
    return (
        session_data
        | {
            "branches": branches,
            "activeBranchId": branch_id,
            "updatedAt": now_iso(),
        },
        merged_branch,
    )


def find_session_branch(session_data: dict[str, Any], branch_id: Any) -> dict[str, Any]:
    if not isinstance(branch_id, str) or not branch_id.strip():
        raise SessionBranchValidationError("branch id is required")
    branches = session_data.get("branches")
    if not isinstance(branches, list):
        raise SessionBranchValidationError("branch not found")
    branch = next((item for item in branches if isinstance(item, dict) and item.get("id") == branch_id), None)
    if branch is None:
        raise SessionBranchValidationError("branch not found")
    return branch


def branch_messages(branch: dict[str, Any]) -> list[dict[str, Any]]:
    messages = branch.get("messages")
    return [item for item in messages if isinstance(item, dict)] if isinstance(messages, list) else []


def session_message_fingerprint(message: dict[str, Any]) -> str:
    role = str(message.get("role") or "unknown")
    content = re.sub(r"\s+", " ", str(message.get("content") or "")).strip()
    return f"{role}::{content}"


def branch_preview(messages: list[dict[str, Any]], selected: set[str]) -> list[str]:
    previews: list[str] = []
    for message in messages:
        if session_message_fingerprint(message) not in selected:
            continue
        content = re.sub(r"\s+", " ", str(message.get("content") or "")).strip()
        previews.append(content if len(content) <= 120 else f"{content[:120]}...")
        if len(previews) >= 5:
            break
    return previews


def copy_session_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "role": message.get("role"),
        "content": message.get("content"),
        "createdAt": message.get("createdAt"),
        "state": message.get("state"),
        "citations": list(message.get("citations") or []),
        "evidence": list(message.get("evidence") or []),
    }


def ensure_unique_session_message_id(message: dict[str, Any], existing_ids: set[str]) -> None:
    message_id = str(message.get("id") or "")
    if not message_id:
        fingerprint_hash = int(sha256_hex(session_message_fingerprint(message))[:8], 16) & 0x7FFFFFFF
        message_id = f"merged-{current_epoch_millis()}-{fingerprint_hash}"
    if message_id in existing_ids:
        message_id = f"{message_id}-m{len(existing_ids)}"
    message["id"] = message_id
    existing_ids.add(message_id)


def sha256_hex(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def current_epoch_millis() -> int:
    return int(time.time() * 1000)
