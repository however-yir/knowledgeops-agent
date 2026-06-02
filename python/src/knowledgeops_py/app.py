from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from .config import Settings, load_settings

TENANT_HEADER = "x-tenant-id"


ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ADMIN": [
        "ROLE_ADMIN",
        "PERM_AUTH_KEY_MANAGE",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_COST_WRITE",
        "PERM_AGENT_TRUSTED",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
    "OPS": [
        "ROLE_OPS",
        "PERM_INGESTION_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
    ],
    "USER": [
        "ROLE_USER",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
}


class AuthTokenResponse(BaseModel):
    ok: int
    msg: str
    token: str | None = None
    refreshToken: str | None = None
    tenantId: str | None = None
    expiresInSeconds: int | None = None
    refreshWillExpireSoon: bool = False


@dataclass
class PlatformStore:
    api_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    refresh_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    latest_files: dict[str, dict[str, Any]] = field(default_factory=dict)
    history_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    trusted_actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    harness_events: list[dict[str, Any]] = field(default_factory=list)
    workflow_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    workflow_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    eval_datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    eval_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    memory_items: list[dict[str, Any]] = field(default_factory=list)
    memory_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    graph_entities: list[dict[str, Any]] = field(default_factory=list)
    graph_relations: list[dict[str, Any]] = field(default_factory=list)
    graph_facts: list[dict[str, Any]] = field(default_factory=list)
    audit_logs: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    cost_budgets: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    store = PlatformStore()
    _seed_demo_key(store, active_settings)
    _seed_business_graph(store, active_settings.demo_tenant_id)
    app = FastAPI(
        title="KnowledgeOps Agent Python Rewrite",
        version="0.1.0",
        docs_url="/swagger-ui/index.html",
        redoc_url=None,
    )
    app.state.settings = active_settings
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        if not request.url.path.startswith("/actuator"):
            app.state.store.audit_logs.append(
                {
                    "auditId": new_id("audit"),
                    "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latencyMs": round((time.perf_counter() - started) * 1000, 2),
                    "createdAt": now_iso(),
                }
            )
        metric_inc(app.state.store, "http_requests_total")
        return response

    @app.get("/actuator/health")
    def health() -> dict[str, str]:
        return {"status": "UP"}

    @app.get("/v3/api-docs")
    def openapi_docs() -> dict[str, Any]:
        return app.openapi()

    @app.get("/actuator/prometheus")
    def prometheus() -> PlainTextResponse:
        lines = [
            "# HELP knowledgeops_python_up Python rewrite liveness.",
            "# TYPE knowledgeops_python_up gauge",
            "knowledgeops_python_up 1",
        ]
        for name, value in sorted(app.state.store.metrics.items()):
            lines.extend([f"# TYPE {name} counter", f"{name} {value:g}"])
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.post("/auth/token", response_model=AuthTokenResponse)
    def token(
        x_api_key: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> AuthTokenResponse:
        identity = authenticate_api_key(store, x_api_key)
        if not identity:
            return AuthTokenResponse(ok=0, msg="invalid api key")
        if x_tenant_id and normalize_tenant(x_tenant_id) != identity["tenantId"]:
            return AuthTokenResponse(ok=0, msg="tenant mismatch for api key")
        return issue_tokens(store, active_settings, identity["principal"], identity["roles"], identity["tenantId"])

    @app.post("/auth/refresh", response_model=AuthTokenResponse)
    def refresh(x_refresh_token: str | None = Header(default=None)) -> AuthTokenResponse:
        if not x_refresh_token:
            return AuthTokenResponse(ok=0, msg="invalid refresh token")
        record = store.refresh_tokens.pop(sha256_hex(x_refresh_token), None)
        if not record or record.get("expiresAt", "") <= now_iso():
            return AuthTokenResponse(ok=0, msg="invalid refresh token")
        return issue_tokens(store, active_settings, record["principal"], record["roles"], record["tenantId"])

    @app.post("/auth/api-keys")
    def issue_api_key(keyName: str = Query(default="py-issued-key"), role: str = Query(default="USER"), tenantId: str | None = Query(default=None)):
        return create_api_key(store, keyName, role, normalize_tenant(tenantId))

    @app.post("/auth/api-keys/rotate")
    def rotate_api_key(keyName: str, role: str = Query(default="USER"), tenantId: str | None = Query(default=None)):
        normalized_tenant = normalize_tenant(tenantId)
        rotated_from = None
        for record in store.api_keys.values():
            if record["keyName"] == keyName and record["tenantId"] == normalized_tenant:
                record["enabled"] = False
                record["revokedAt"] = now_iso()
                record["revokedReason"] = "rotated"
                rotated_from = record["keyHash"]
        issued = create_api_key(store, keyName, role, normalized_tenant)
        if rotated_from:
            store.api_keys[sha256_hex(issued["rawApiKey"])]["rotatedFromId"] = rotated_from
        issued["msg"] = "rotated"
        return issued

    @app.post("/auth/api-keys/revoke")
    def revoke_api_key(keyName: str, tenantId: str | None = Query(default=None)):
        normalized_tenant = normalize_tenant(tenantId)
        for record in store.api_keys.values():
            if record["keyName"] == keyName and record["tenantId"] == normalized_tenant:
                record["enabled"] = False
                record["revokedAt"] = now_iso()
                record["revokedReason"] = "manual revoke"
        return {"ok": 1, "msg": "revoked", "keyName": keyName, "tenantId": normalized_tenant}

    @app.post("/ai/react/chat")
    async def react_chat_route(request: Request):
        body = await json_body(request)
        return react_chat(store, normalize_tenant(request.headers.get(TENANT_HEADER)), body, "react")

    @app.post("/ai/react/chat/stream")
    async def react_stream_route(request: Request):
        body = await json_body(request)
        payload = react_chat(store, normalize_tenant(request.headers.get(TENANT_HEADER)), body, "react")
        return PlainTextResponse(to_sse(payload), media_type="text/event-stream")

    @app.api_route("/ai/chat", methods=["GET", "POST"], response_class=PlainTextResponse)
    async def chat(request: Request, prompt: str = "", chatId: str = "", modelProfile: str | None = None):
        body = await json_body(request)
        payload = chat_request(prompt, chatId, modelProfile, body)
        return react_chat(store, normalize_tenant(request.headers.get(TENANT_HEADER)), payload, "chat")["answer"]

    @app.api_route("/ai/service", methods=["GET", "POST"], response_class=PlainTextResponse)
    async def service(request: Request, prompt: str = "", chatId: str = "", modelProfile: str | None = None):
        body = await json_body(request)
        payload = chat_request(prompt, chatId, modelProfile, body)
        return react_chat(store, normalize_tenant(request.headers.get(TENANT_HEADER)), payload, "service")["answer"]

    @app.api_route("/ai/pdf/chat", methods=["GET", "POST"], response_class=PlainTextResponse)
    async def pdf_chat(request: Request, prompt: str = "", chatId: str = "", modelProfile: str | None = None):
        body = await json_body(request)
        payload = chat_request(prompt, chatId, modelProfile, body)
        result = react_chat(store, normalize_tenant(request.headers.get(TENANT_HEADER)), payload, "pdf")
        citations = "\n".join(f"[{index + 1}] {citation}" for index, citation in enumerate(result.get("citations", [])))
        return f"{result['answer']}\n\n引用来源:\n{citations}" if citations else result["answer"]

    @app.post("/ai/feedback")
    async def feedback(request: Request):
        body = await json_body(request)
        store.feedback.append({"tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)), **body, "createdAt": now_iso()})
        return {"ok": 1, "msg": "ok"}

    @app.post("/ingestion/upload/{chat_id}")
    @app.post("/ai/pdf/upload/{chat_id}")
    async def upload(chat_id: str, request: Request):
        tenant_id = normalize_tenant(request.headers.get(TENANT_HEADER))
        source_name, content = await request_file(request)
        idempotency_key = request.headers.get("x-idempotency-key") or sha256_hex(f"{tenant_id}:{chat_id}:{source_name}:{sha256_hex(content)}")
        existing = next((job for job in store.jobs.values() if job["tenantId"] == tenant_id and job["idempotencyKey"] == idempotency_key), None)
        if existing:
            return {"ok": 1, "msg": "accepted", "job": existing}
        job_id = new_id("job")
        now = now_iso()
        text = safe_decode(content)
        job = {
            "jobId": job_id,
            "tenantId": tenant_id,
            "chatId": chat_id,
            "sourceName": source_name,
            "sourceType": "pdf" if source_name.lower().endswith(".pdf") else "text",
            "status": "COMPLETED",
            "attemptCount": 1,
            "maxRetries": 3,
            "traceId": new_id("trace"),
            "queueBackend": "local",
            "idempotencyKey": idempotency_key,
            "contentHash": sha256_hex(content),
            "createdAt": now,
            "startedAt": now,
            "finishedAt": now,
            "updatedAt": now,
        }
        store.jobs[job_id] = job
        store.latest_files[f"{tenant_id}:{chat_id}"] = {"sourceName": source_name, "content": content, "contentType": "application/octet-stream"}
        for index, chunk in enumerate(chunk_text(text)):
            store.chunks.append(
                {
                    "chunkId": new_id("chunk"),
                    "tenantId": tenant_id,
                    "chatId": chat_id,
                    "jobId": job_id,
                    "fileName": source_name,
                    "chunkIndex": index,
                    "content": chunk,
                    "tokens": set(tokenize(chunk)),
                    "createdAt": now,
                }
            )
        save_session(store, tenant_id, "pdf", chat_id)
        return {"ok": 1, "msg": "accepted", "job": public_job(job)}

    @app.get("/ai/pdf/file/{chat_id}")
    def download_pdf(chat_id: str, x_tenant_id: str | None = Header(default=None)):
        latest = store.latest_files.get(f"{normalize_tenant(x_tenant_id)}:{chat_id}")
        if not latest:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
        return Response(
            latest["content"],
            media_type=latest["contentType"],
            headers={"Content-Disposition": f'attachment; filename="{latest["sourceName"]}"'},
        )

    @app.get("/ingestion/jobs/{job_id}")
    def get_job(job_id: str, x_tenant_id: str | None = Header(default=None)):
        job = store.jobs.get(job_id)
        if not job or job["tenantId"] != normalize_tenant(x_tenant_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return public_job(job)

    @app.get("/ingestion/jobs")
    def list_jobs(chatId: str = "", limit: int = 20, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        return [
            public_job(job)
            for job in list(store.jobs.values())[-bounded(limit, 1, 100) :]
            if job["tenantId"] == tenant_id and (not chatId or job["chatId"] == chatId)
        ]

    @app.post("/ingestion/jobs/process")
    def process_job(jobId: str | None = Query(default=None)):
        return {"ok": 1, "msg": f"processed {jobId}" if jobId else "no queued jobs", "job": store.jobs.get(jobId) if jobId else None}

    @app.get("/ai/history/{history_type}")
    def history_list(history_type: str, page: int = 1, pageSize: int = 20, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        sessions = [
            session
            for session in store.history_sessions.values()
            if session["tenantId"] == tenant_id and session["type"] == history_type
        ]
        sessions.sort(key=lambda item: item["updatedAt"], reverse=True)
        return page_result([item["chatId"] for item in sessions], page, pageSize)

    @app.get("/ai/history/{history_type}/{chat_id}")
    def history_messages(history_type: str, chat_id: str, page: int = 1, pageSize: int = 50, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        conversation_id = build_conversation_id(history_type, chat_id)
        messages = [
            {"role": message["role"], "content": message["content"]}
            for message in store.conversations
            if message["tenantId"] == tenant_id and message["conversationId"] == conversation_id
        ]
        messages.reverse()
        return page_result(messages, page, pageSize)

    @app.get("/ai/sessions")
    def list_sessions(page: int = 1, pageSize: int = 20, includeArchived: str = "false"):
        sessions = [session for session in store.sessions.values() if includeArchived == "true" or not session.get("archived")]
        return page_result(sessions, page, pageSize)

    @app.get("/ai/sessions/{session_id}")
    def get_session(session_id: str):
        return session_get(store, session_id)

    @app.put("/ai/sessions/{session_id}")
    async def upsert_session(session_id: str, request: Request):
        body = await json_body(request)
        body["id"] = session_id
        body["updatedAt"] = epoch_ms()
        store.sessions[session_id] = body
        return body

    @app.post("/ai/sessions/{session_id}/pin")
    def pin_session(session_id: str, value: str = "false"):
        session = session_get(store, session_id)
        session["pinned"] = value == "true"
        session["updatedAt"] = epoch_ms()
        return session

    @app.post("/ai/sessions/{session_id}/archive")
    def archive_session(session_id: str, value: str = "false"):
        session = session_get(store, session_id)
        session["archived"] = value == "true"
        session["updatedAt"] = epoch_ms()
        return session

    @app.post("/ai/sessions/{session_id}/branches/compare")
    async def compare_branches(session_id: str, request: Request):
        body = await json_body(request)
        session = session_get(store, session_id)
        source = find_branch(session, str(body.get("sourceBranchId", "")))
        target = find_branch(session, str(body.get("targetBranchId", "")))
        source_messages = source.get("messages", []) if source else []
        target_messages = target.get("messages", []) if target else []
        target_ids = {message.get("id") for message in target_messages}
        source_ids = {message.get("id") for message in source_messages}
        return {
            "sourceBranchId": body.get("sourceBranchId"),
            "targetBranchId": body.get("targetBranchId"),
            "sourceMessageCount": len(source_messages),
            "targetMessageCount": len(target_messages),
            "commonMessageCount": len([message for message in source_messages if message.get("id") in target_ids]),
            "sourceOnlyCount": len([message for message in source_messages if message.get("id") not in target_ids]),
            "targetOnlyCount": len([message for message in target_messages if message.get("id") not in source_ids]),
        }

    @app.post("/ai/sessions/{session_id}/branches/merge")
    async def merge_branches(session_id: str, request: Request):
        body = await json_body(request)
        session = session_get(store, session_id)
        source = find_branch(session, str(body.get("sourceBranchId", ""))) or {"messages": [], "traceSteps": []}
        target = find_branch(session, str(body.get("targetBranchId", ""))) or {"messages": [], "traceSteps": []}
        seen = {message.get("id") for message in target.get("messages", [])}
        merged = {
            "id": f"merge-{epoch_ms()}",
            "title": body.get("title") or "Merged branch",
            "parentBranchId": target.get("id"),
            "parentMessageId": None,
            "updatedAt": epoch_ms(),
            "messages": [*target.get("messages", []), *[message for message in source.get("messages", []) if message.get("id") not in seen]],
            "traceSteps": [*target.get("traceSteps", []), *source.get("traceSteps", [])],
        }
        session["branches"].append(merged)
        session["activeBranchId"] = merged["id"]
        return {"session": session, "mergedBranch": merged, "mergedMessageCount": len(merged["messages"])}

    @app.get("/ai/harness/actions")
    def harness_actions():
        return action_catalog()

    @app.post("/ai/harness/actions/preview")
    async def harness_preview(request: Request):
        body = await json_body(request)
        token_value = new_id("ta")
        decision = evaluate_policy(body)
        expires_at = future_iso(minutes=5)
        store.trusted_actions[token_value] = {**body, "expiresAt": expires_at, "decision": decision}
        return {
            "ok": 1 if decision["allowed"] else 0,
            "token": token_value,
            "action": body.get("action", "unknown"),
            "expiresAt": expires_at,
            "preview": {"status": "pending_confirmation" if decision["allowed"] else "blocked", "request": body, "decision": decision},
        }

    @app.post("/ai/harness/actions/execute/{token_value}")
    def harness_execute(token_value: str):
        started = time.perf_counter()
        request = store.trusted_actions.pop(token_value, None)
        if not request:
            return {"status": "not_found", "source": "trusted-action"}
        if request.get("expiresAt", "") <= now_iso():
            return {"status": "expired", "source": "trusted-action"}
        decision = evaluate_policy(request)
        if not decision["allowed"]:
            return record_harness_event(store, request, "policy", "blocked", started, {"error": decision["message"]})
        observation = execute_harness_action(store, request)
        return record_harness_event(store, request, observation["source"], "executed", started, observation)

    @app.get("/ai/workflow/tasks/{task_id}")
    def workflow_task(task_id: str):
        return store.workflow_tasks.get(task_id) or {"ok": 0, "msg": "task not found"}

    @app.get("/ai/workflow/tasks/{task_id}/events")
    def workflow_events(task_id: str):
        return store.workflow_events.get(task_id, [])

    @app.get("/ai/workflow/tasks")
    def workflow_tasks(page: int = 1, pageSize: int = 20, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        tasks = [task for task in store.workflow_tasks.values() if task["tenantId"] == tenant_id]
        tasks.sort(key=lambda item: item["updatedAt"], reverse=True)
        return page_result(tasks, page, pageSize)

    @app.post("/ai/research/tasks")
    async def research_task(request: Request):
        body = await json_body(request)
        tenant_id = normalize_tenant(request.headers.get(TENANT_HEADER))
        prompt = str(body.get("topic") or body.get("prompt") or "research")
        task = create_workflow_task(store, tenant_id, "research", prompt, body.get("modelProfile"))
        task["finalOutput"] = f"# Research Report\n\n- Topic: {prompt}\n- Finding: Python rewrite generated a deterministic research report."
        task["status"] = "DONE"
        task["updatedAt"] = now_iso()
        append_workflow_event(store, task["taskId"], "TASK_COMPLETED", {"report": task["finalOutput"]})
        return {"ok": 1, "taskId": task["taskId"], "report": task["finalOutput"], "task": task}

    @app.get("/ai/research/tasks/{task_id}")
    def research_get(task_id: str):
        return store.workflow_tasks.get(task_id) or {"ok": 0, "msg": "task not found"}

    @app.get("/ai/research/tasks/{task_id}/events")
    def research_events(task_id: str):
        return store.workflow_events.get(task_id, [])

    @app.get("/ai/research/tasks/{task_id}/report")
    def research_report(task_id: str):
        task = store.workflow_tasks.get(task_id)
        return {"taskId": task_id, "report": task.get("finalOutput")} if task else {"ok": 0, "msg": "task not found"}

    @app.post("/ai/workflow/react/chat")
    async def workflow_react(request: Request):
        body = await json_body(request)
        tenant_id = normalize_tenant(request.headers.get(TENANT_HEADER))
        create_workflow_task(store, tenant_id, "react", str(body.get("prompt", "")), body.get("modelProfile"), body.get("chatId"), body.get("sessionId"))
        return react_chat(store, tenant_id, body, "workflow_react")

    @app.post("/ai/workflow/react/chat/stream")
    async def workflow_react_stream(request: Request):
        body = await json_body(request)
        tenant_id = normalize_tenant(request.headers.get(TENANT_HEADER))
        create_workflow_task(store, tenant_id, "react", str(body.get("prompt", "")), body.get("modelProfile"), body.get("chatId"), body.get("sessionId"))
        return PlainTextResponse(to_sse(react_chat(store, tenant_id, body, "workflow_react")), media_type="text/event-stream")

    @app.post("/ai/evaluation/datasets")
    async def create_dataset(request: Request):
        body = await json_body(request)
        if not str(body.get("name", "")).strip():
            return {"ok": 0, "msg": "dataset name is required"}
        if not body.get("cases"):
            return {"ok": 0, "msg": "dataset cases are required"}
        now = now_iso()
        dataset = {
            "datasetId": new_id("ds"),
            "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
            "name": str(body["name"]).strip(),
            "description": body.get("description"),
            "cases": body.get("cases", []),
            "caseCount": len(body.get("cases", [])),
            "createdAt": now,
            "updatedAt": now,
        }
        store.eval_datasets[dataset["datasetId"]] = dataset
        return dataset

    @app.get("/ai/evaluation/datasets")
    def list_datasets(x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        return [
            {key: value for key, value in dataset.items() if key != "cases"} | {"caseCount": len(dataset.get("cases", []))}
            for dataset in store.eval_datasets.values()
            if dataset["tenantId"] == tenant_id
        ]

    @app.post("/ai/evaluation/datasets/{dataset_id}/runs")
    async def trigger_run(dataset_id: str, request: Request):
        body = await json_body(request)
        dataset = store.eval_datasets.get(dataset_id)
        if not dataset:
            return {"ok": 0, "msg": "dataset not found"}
        results = []
        for index, test_case in enumerate(dataset.get("cases", [])):
            answer = react_chat(
                store,
                dataset["tenantId"],
                {"prompt": str(test_case.get("question", "")), "chatId": str(test_case.get("chatId") or f"eval-{dataset_id}-{index}")},
                "eval",
            )
            expected = [str(item).lower() for item in test_case.get("expectedKeywords", [])]
            pool = f"{answer['answer']} {' '.join(answer.get('evidence', []))}".lower()
            keyword_score = 1 if not expected else len([keyword for keyword in expected if keyword in pool]) / len(expected)
            score = round4(0.5 + keyword_score * 0.5)
            results.append(
                {
                    "resultId": new_id("res"),
                    "caseId": str(test_case.get("caseId") or f"case-{index + 1}"),
                    "status": "PASSED" if score >= 0.7 else "FAILED",
                    "question": test_case.get("question", ""),
                    "answer": answer["answer"],
                    "citations": answer.get("citations", []),
                    "evidence": answer.get("evidence", []),
                    "retrievalHit": 1 if answer.get("evidence") else 0,
                    "citationCoverage": 1 if answer.get("citations") else 0,
                    "keywordScore": score,
                    "answerFaithfulness": 1 if answer.get("citations") else 0.5,
                    "score": score,
                    "latencyMs": 1,
                }
            )
        total = len(results)
        passed = len([result for result in results if result["status"] == "PASSED"])
        run = {
            "runId": new_id("run"),
            "datasetId": dataset_id,
            "tenantId": dataset["tenantId"],
            "status": "COMPLETED",
            "modelProfile": body.get("modelProfile", "balanced"),
            "metrics": {
                "totalCases": total,
                "passedCases": passed,
                "runScore": round4(sum(result["score"] for result in results) / max(1, total)),
                "retrievalHitRate": round4(sum(result["retrievalHit"] for result in results) / max(1, total)),
                "citationCoverageRate": round4(sum(result["citationCoverage"] for result in results) / max(1, total)),
                "answerFaithfulnessScore": round4(sum(result["answerFaithfulness"] for result in results) / max(1, total)),
                "avgLatencyMs": 1,
                "failureRate": round4((total - passed) / max(1, total)),
            },
            "results": results,
            "createdAt": now_iso(),
            "startedAt": now_iso(),
            "finishedAt": now_iso(),
        }
        store.eval_runs[run["runId"]] = run
        return run

    @app.get("/ai/evaluation/datasets/{dataset_id}/comparison")
    def eval_comparison(dataset_id: str):
        dataset = store.eval_datasets.get(dataset_id)
        runs = [run for run in store.eval_runs.values() if run["datasetId"] == dataset_id]
        baseline = store.eval_runs.get(dataset.get("baselineRunId")) if dataset and dataset.get("baselineRunId") else (runs[-2] if len(runs) >= 2 else None)
        return {"dataset": dataset, "baseline": baseline, "current": runs[-1] if runs else None}

    @app.get("/ai/evaluation/runs/{run_id}")
    def eval_run(run_id: str):
        return store.eval_runs.get(run_id) or {"ok": 0, "msg": "run not found"}

    @app.post("/ai/evaluation/runs/{run_id}/baseline")
    def eval_baseline(run_id: str):
        run = store.eval_runs.get(run_id)
        dataset = store.eval_datasets.get(run["datasetId"]) if run else None
        if run and dataset:
            dataset["baselineRunId"] = run_id
        return run or {"ok": 0, "msg": "run not found"}

    @app.get("/ai/evaluation/runs/{run_id}/report")
    def eval_report(run_id: str):
        run = store.eval_runs.get(run_id)
        lines = [
            "# RAG Evaluation Report",
            "",
            f"- Run: {run_id}",
            f"- Status: {run.get('status') if run else 'not_found'}",
            f"- Score: {run.get('metrics', {}).get('runScore', 0) if run else 0}",
            f"- Passed Cases: {run.get('metrics', {}).get('passedCases', 0) if run else 0}/{run.get('metrics', {}).get('totalCases', 0) if run else 0}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/markdown;charset=UTF-8")

    @app.get("/cost/summary")
    def cost_summary(x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        budget = store.cost_budgets.get(tenant_id, default_budget(tenant_id))
        usage = store.usage.get(tenant_id, default_usage(tenant_id))
        return {"tenantId": tenant_id, "budget": budget, "usage": usage, "remainingBudgetUsd": round4(budget["monthlyBudgetUsd"] - usage["totalCostUsd"])}

    @app.post("/cost/budget")
    async def update_budget(request: Request):
        body = await json_body(request)
        tenant_id = normalize_tenant(body.get("tenantId") or request.headers.get(TENANT_HEADER))
        budget = {
            "tenantId": tenant_id,
            "monthlyBudgetUsd": float(body.get("monthlyBudgetUsd", 25)),
            "hardLimitEnabled": bool(body.get("hardLimitEnabled", False)),
            "updatedAt": now_iso(),
        }
        store.cost_budgets[tenant_id] = budget
        return budget

    @app.get("/audit/logs")
    def audit_logs(limit: int = 50, tenantId: str | None = None):
        bounded_limit = bounded(limit, 1, 200)
        logs = [log for log in store.audit_logs if not tenantId or log["tenantId"] == tenantId]
        return list(reversed(logs[-bounded_limit:]))

    @app.get("/ai/memory/items")
    def list_memory(userId: str = "anonymous", type: str | None = None, limit: int = 20, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        now = now_iso()
        items = [
            item
            for item in store.memory_items
            if item["tenantId"] == tenant_id
            and item["userId"] == userId
            and (not type or item["type"] == type)
            and (not item.get("expiresAt") or item["expiresAt"] > now)
        ]
        items.sort(key=lambda item: item["updatedAt"], reverse=True)
        return items[: bounded(limit, 1, 100)]

    @app.post("/ai/memory/items")
    async def add_memory(request: Request):
        body = await json_body(request)
        content = str(body.get("content", "")).strip()
        if not content:
            return {"ok": 0, "msg": "memory content is required"}
        now = now_iso()
        item = {
            "memoryId": new_id("mem"),
            "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
            "userId": str(body.get("userId") or "anonymous"),
            "type": str(body.get("type") or "long"),
            "content": content,
            "source": body.get("source"),
            "sourceTaskId": body.get("sourceTaskId"),
            "confidence": clamp(float(body.get("confidence", 0.85)), 0, 1),
            "expiresAt": body.get("expiresAt"),
            "createdAt": now,
            "updatedAt": now,
        }
        store.memory_items.append(item)
        append_memory_event(store, item["memoryId"], "CREATE", f"saved {item['type']} memory")
        return item

    @app.delete("/ai/memory/items/{memory_id}")
    def delete_memory(memory_id: str):
        before = len(store.memory_items)
        store.memory_items[:] = [item for item in store.memory_items if item["memoryId"] != memory_id]
        if len(store.memory_items) == before:
            return {"ok": 0, "msg": "memory not found"}
        append_memory_event(store, memory_id, "DELETE", "manual deletion")
        return {"ok": 1, "msg": "deleted"}

    @app.get("/ai/memory/items/{memory_id}/events")
    def memory_events(memory_id: str):
        return store.memory_events.get(memory_id, [])

    @app.get("/ai/memory/context")
    def memory_context(userId: str = "anonymous", prompt: str = "", limit: int = 8, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        tokens = set(tokenize(prompt))
        items = []
        for item in store.memory_items:
            if item["tenantId"] != tenant_id or item["userId"] != userId:
                continue
            relevance = clamp(len(tokens.intersection(tokenize(item["content"]))) / max(1, len(tokens)) + item["confidence"] * 0.2, 0, 1)
            items.append({**item, "relevance": relevance})
        items.sort(key=lambda item: (item["relevance"], item["updatedAt"]), reverse=True)
        selected = items[: bounded(limit, 1, 50)]
        return {"userId": userId, "tenantId": tenant_id, "items": selected, "snapshot": "\n".join(f"[{item['type']}:{item['confidence']}] {item['content']}" for item in selected)}

    @app.post("/ai/memory/cleanup")
    def cleanup_memory(x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        before = len(store.memory_items)
        now = now_iso()
        store.memory_items[:] = [item for item in store.memory_items if not (item["tenantId"] == tenant_id and item.get("expiresAt") and item["expiresAt"] <= now)]
        return {"ok": 1, "removed": before - len(store.memory_items)}

    @app.get("/ai/graph/entities")
    def graph_entities(q: str = "", type: str | None = None, limit: int = 50, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        query = q.lower().strip()
        entities = [
            entity
            for entity in store.graph_entities
            if entity["tenantId"] == tenant_id
            and (not type or entity["type"] == type)
            and (not query or query in f"{entity['name']} {entity.get('description', '')} {' '.join(entity.get('aliases', []))}".lower())
        ]
        return entities[: bounded(limit, 1, 100)]

    @app.post("/ai/graph/entities")
    async def add_graph_entity(request: Request):
        body = await json_body(request)
        name = str(body.get("name", "")).strip()
        if not name:
            return {"ok": 0, "msg": "entity name is required"}
        now = now_iso()
        entity = {
            "entityId": new_id("kgent"),
            "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
            "name": name,
            "type": str(body.get("type") or "UNKNOWN"),
            "description": body.get("description"),
            "aliases": body.get("aliases") or [],
            "metadata": body.get("metadata") or {},
            "createdAt": now,
            "updatedAt": now,
        }
        store.graph_entities.append(entity)
        return entity

    @app.post("/ai/graph/relations")
    async def add_graph_relation(request: Request):
        body = await json_body(request)
        if not body.get("sourceEntityId") or not body.get("targetEntityId"):
            return {"ok": 0, "msg": "sourceEntityId and targetEntityId are required"}
        now = now_iso()
        relation = {
            "relationId": new_id("kgrel"),
            "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
            "sourceEntityId": body["sourceEntityId"],
            "targetEntityId": body["targetEntityId"],
            "relationType": body.get("relationType") or "RELATED_TO",
            "weight": clamp(float(body.get("weight", 1)), 0, 1),
            "metadata": body.get("metadata") or {},
            "createdAt": now,
            "updatedAt": now,
        }
        store.graph_relations.append(relation)
        return relation

    @app.get("/ai/graph/entities/{entity_id}/neighbors")
    def graph_neighbors(entity_id: str, limit: int = 50, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        relations = [
            relation
            for relation in store.graph_relations
            if relation["tenantId"] == tenant_id and (relation["sourceEntityId"] == entity_id or relation["targetEntityId"] == entity_id)
        ][: bounded(limit, 1, 100)]
        entity_ids = {relation["sourceEntityId"] for relation in relations} | {relation["targetEntityId"] for relation in relations}
        entities = [entity for entity in store.graph_entities if entity["tenantId"] == tenant_id and entity["entityId"] in entity_ids]
        return {"entityId": entity_id, "relations": relations, "entities": entities}

    @app.post("/ai/graph/facts")
    async def add_graph_fact(request: Request):
        body = await json_body(request)
        if not str(body.get("subject", "")).strip() or not str(body.get("predicate", "")).strip() or not str(body.get("object", "")).strip():
            return {"ok": 0, "msg": "subject, predicate and object are required"}
        now = now_iso()
        fact = {
            "factId": new_id("kgfact"),
            "tenantId": normalize_tenant(request.headers.get(TENANT_HEADER)),
            "subject": str(body["subject"]).strip(),
            "predicate": str(body["predicate"]).strip(),
            "object": str(body["object"]).strip(),
            "confidence": clamp(float(body.get("confidence", 0.7)), 0, 1),
            "source": body.get("source"),
            "metadata": body.get("metadata") or {},
            "createdAt": now,
            "updatedAt": now,
        }
        store.graph_facts.append(fact)
        return fact

    @app.get("/ai/graph/facts")
    def graph_facts(query: str = "", limit: int = 50, x_tenant_id: str | None = Header(default=None)):
        tenant_id = normalize_tenant(x_tenant_id)
        normalized = query.lower().strip()
        facts = [
            fact
            for fact in store.graph_facts
            if fact["tenantId"] == tenant_id
            and (not normalized or normalized in f"{fact['subject']} {fact['predicate']} {fact['object']}".lower())
        ]
        return facts[: bounded(limit, 1, 100)]

    return app


def react_chat(store: PlatformStore, tenant_id: str, request: dict[str, Any], history_type: str) -> dict[str, Any]:
    prompt = str(request.get("prompt") or "")
    chat_id = str(request.get("chatId") or "")
    profile = str(request.get("modelProfile") or "balanced")
    rag = retrieve(store, tenant_id, chat_id, prompt)
    route = route_model(profile, history_type)
    answer = compose_answer(prompt, rag["evidence"])
    input_tokens = estimate_tokens("\n".join([prompt, *rag["evidence"]]))
    output_tokens = estimate_tokens(answer)
    record_usage(store, tenant_id, input_tokens, output_tokens)
    metric_inc(store, "react_requests_total")
    response = {
        "ok": 1,
        "msg": "ok",
        "chatId": chat_id,
        "answer": answer,
        "citations": rag["citations"],
        "evidence": rag["evidence"],
        "routeProfile": route["profile"],
        "routeReason": route["reason"],
        "routeCostTier": route["costTier"],
        "experimentKey": route["experimentKey"],
        "experimentVariant": route["experimentVariant"],
        "experimentBucket": route["experimentBucket"],
        "trace": [
            {
                "step": 1,
                "thought": "Resolve model profile and hybrid retrieval context.",
                "action": "hybrid_retrieve",
                "actionInput": {"prompt": prompt, "chatId": chat_id, "tenantId": tenant_id, "model": route["model"]},
                "observation": {"citations": len(rag["citations"]), "evidence": len(rag["evidence"]), "retrievalStats": rag["retrievalStats"]},
            },
            {
                "step": 2,
                "thought": "Generate a deterministic grounded answer for local parity.",
                "action": "local_fallback",
                "observation": {"status": "completed", "model": "local-grounded", "degraded": True, "inputTokens": input_tokens, "outputTokens": output_tokens},
            },
        ],
    }
    if chat_id.strip():
        append_exchange(store, tenant_id, history_type, chat_id, prompt, answer)
    return response


def retrieve(store: PlatformStore, tenant_id: str, chat_id: str, prompt: str) -> dict[str, Any]:
    tokens = set(tokenize(prompt))
    scored = []
    for chunk in store.chunks:
        if chunk["tenantId"] != tenant_id or (chat_id and chunk["chatId"] != chat_id):
            continue
        score = len(tokens.intersection(chunk["tokens"])) / max(1, len(tokens))
        if score > 0 or not tokens:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for _, chunk in scored[:5]]
    evidence = [chunk["content"] for chunk in selected]
    citations = [f"source={chunk['fileName']}, chunk={chunk['chunkIndex'] + 1}" for chunk in selected]
    return {"evidence": evidence, "citations": citations, "retrievalStats": {"localChunkCount": len(scored), "selectedCount": len(selected)}}


def compose_answer(prompt: str, evidence: list[str]) -> str:
    if evidence:
        markers = " ".join(f"[{index + 1}]" for index in range(len(evidence)))
        return f"基于已入库知识，问题“{prompt}”的答案如下：{evidence[0][:240]} {markers}"
    if prompt:
        return f"Python KnowledgeOps local answer: {prompt}"
    return "Python KnowledgeOps service is ready."


def to_sse(response: dict[str, Any]) -> str:
    trace = "".join(f"event: trace\ndata: {json.dumps(step, ensure_ascii=False)}\n\n" for step in response["trace"])
    token = f"event: token\ndata: {json.dumps({'token': response['answer']}, ensure_ascii=False)}\n\n"
    done = f"event: done\ndata: {json.dumps(response, ensure_ascii=False)}\n\n"
    return f"{trace}{token}{done}"


def issue_tokens(store: PlatformStore, settings: Settings, principal: str, roles: list[str], tenant_id: str) -> AuthTokenResponse:
    permissions = sorted({permission for role in roles for permission in ROLE_PERMISSIONS.get(role, [])})
    token_payload = {"sub": principal, "roles": roles, "permissions": permissions, "tenant_id": tenant_id, "iat": epoch_ms()}
    token = "pyjwt." + base64.urlsafe_b64encode(json.dumps(token_payload).encode("utf-8")).decode("ascii").rstrip("=")
    refresh_token = new_id("refresh")
    store.refresh_tokens[sha256_hex(refresh_token)] = {
        "principal": principal,
        "roles": roles,
        "tenantId": tenant_id,
        "expiresAt": future_iso(days=7),
        "createdAt": now_iso(),
    }
    return AuthTokenResponse(ok=1, msg="ok", token=token, refreshToken=refresh_token, tenantId=tenant_id, expiresInSeconds=settings.token_ttl_seconds)


def authenticate_api_key(store: PlatformStore, api_key: str | None) -> dict[str, Any] | None:
    if not api_key:
        return None
    record = store.api_keys.get(sha256_hex(api_key.strip()))
    if not record or not record.get("enabled", False) or record.get("revokedAt"):
        return None
    record["lastUsedAt"] = now_iso()
    return {"principal": record["keyName"], "roles": [record["roleName"]], "tenantId": record["tenantId"], "source": "api_key"}


def create_api_key(store: PlatformStore, key_name: str, role: str, tenant_id: str) -> dict[str, Any]:
    raw = "koa_" + uuid4().hex + uuid4().hex[:16]
    record = {
        "keyHash": sha256_hex(raw),
        "keyName": key_name,
        "roleName": role or "USER",
        "tenantId": tenant_id,
        "enabled": True,
        "expiresAt": future_iso(days=30),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    store.api_keys[record["keyHash"]] = record
    return {"ok": 1, "msg": "ok", "keyName": key_name, "tenantId": tenant_id, "rawApiKey": raw, "expiresAt": record["expiresAt"]}


def _seed_demo_key(store: PlatformStore, settings: Settings) -> None:
    store.api_keys[sha256_hex(settings.demo_api_key)] = {
        "keyHash": sha256_hex(settings.demo_api_key),
        "keyName": "local-demo",
        "roleName": "ADMIN",
        "tenantId": settings.demo_tenant_id,
        "enabled": True,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def _seed_business_graph(store: PlatformStore, tenant_id: str) -> None:
    school = {"entityId": new_id("kgent"), "tenantId": tenant_id, "name": "KnowledgeOps", "type": "PLATFORM", "description": "Enterprise RAG and agent platform", "aliases": ["KOA"], "metadata": {}, "createdAt": now_iso(), "updatedAt": now_iso()}
    course = {"entityId": new_id("kgent"), "tenantId": tenant_id, "name": "Python Rewrite", "type": "CONCEPT", "description": "Python parity rewrite track", "aliases": ["python-rewrite"], "metadata": {}, "createdAt": now_iso(), "updatedAt": now_iso()}
    store.graph_entities.extend([school, course])
    store.graph_relations.append({"relationId": new_id("kgrel"), "tenantId": tenant_id, "sourceEntityId": school["entityId"], "targetEntityId": course["entityId"], "relationType": "HAS_TRACK", "weight": 1, "metadata": {}, "createdAt": now_iso(), "updatedAt": now_iso()})
    store.graph_facts.append({"factId": new_id("kgfact"), "tenantId": tenant_id, "subject": "contract", "predicate": "covers", "object": "graph facts", "confidence": 0.9, "source": "seed", "metadata": {}, "createdAt": now_iso(), "updatedAt": now_iso()})


async def request_file(request: Request) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if hasattr(file, "read"):
            return getattr(file, "filename", "document.txt") or "document.txt", await file.read()
    body = await request.body()
    return "document.txt", body


async def json_body(request: Request) -> dict[str, Any]:
    if request.method in {"GET", "DELETE"}:
        return {}
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def chat_request(prompt: str, chat_id: str, model_profile: str | None, body: dict[str, Any]) -> dict[str, Any]:
    return {"prompt": prompt or body.get("prompt", ""), "chatId": chat_id or body.get("chatId", ""), "modelProfile": model_profile or body.get("modelProfile")}


def save_session(store: PlatformStore, tenant_id: str, history_type: str, chat_id: str) -> None:
    if not chat_id:
        return
    store.history_sessions[f"{tenant_id}:{history_type}:{chat_id}"] = {
        "tenantId": tenant_id,
        "type": history_type,
        "chatId": chat_id,
        "conversationId": build_conversation_id(history_type, chat_id),
        "updatedAt": now_iso(),
    }


def append_exchange(store: PlatformStore, tenant_id: str, history_type: str, chat_id: str, prompt: str, answer: str) -> None:
    save_session(store, tenant_id, history_type, chat_id)
    conversation_id = build_conversation_id(history_type, chat_id)
    if prompt.strip():
        store.conversations.append({"tenantId": tenant_id, "conversationId": conversation_id, "role": "user", "content": prompt, "createdAt": now_iso()})
    if answer.strip():
        store.conversations.append({"tenantId": tenant_id, "conversationId": conversation_id, "role": "assistant", "content": answer, "createdAt": now_iso()})


def session_get(store: PlatformStore, session_id: str) -> dict[str, Any]:
    if session_id not in store.sessions:
        store.sessions[session_id] = {
            "id": session_id,
            "title": "New Python session",
            "updatedAt": epoch_ms(),
            "modelProfile": "balanced",
            "streaming": False,
            "pinned": False,
            "archived": False,
            "workspaceId": "default",
            "activeBranchId": "main",
            "branches": [{"id": "main", "title": "Main", "parentBranchId": None, "parentMessageId": None, "updatedAt": epoch_ms(), "messages": [], "traceSteps": []}],
        }
    return store.sessions[session_id]


def find_branch(session: dict[str, Any], branch_id: str) -> dict[str, Any] | None:
    return next((branch for branch in session.get("branches", []) if branch.get("id") == branch_id), None)


def action_catalog() -> list[dict[str, Any]]:
    return [
        {"action": "query_school", "runtime": "builtin", "requiredKeys": [], "optionalKeys": [], "riskLevel": "read", "trustedOnly": False},
        {"action": "query_course", "runtime": "builtin", "requiredKeys": [], "optionalKeys": ["type", "edu", "sorts"], "riskLevel": "read", "trustedOnly": False},
        {"action": "add_course_reservation", "runtime": "builtin", "requiredKeys": ["course", "studentName", "contactInfo", "school"], "optionalKeys": ["remark"], "riskLevel": "write", "trustedOnly": False, "sensitiveKeys": ["contactInfo"]},
        {"action": "rag_search", "runtime": "builtin", "requiredKeys": [], "optionalKeys": ["query", "tenantId", "chatId"], "riskLevel": "read", "trustedOnly": False},
        {"action": "workspace_list_files", "runtime": "workspace", "requiredKeys": [], "optionalKeys": ["path", "maxDepth"], "riskLevel": "read", "trustedOnly": True},
        {"action": "workspace_read_file", "runtime": "workspace", "requiredKeys": ["path"], "optionalKeys": ["maxBytes"], "riskLevel": "read", "trustedOnly": True},
        {"action": "workspace_search_text", "runtime": "workspace", "requiredKeys": ["query"], "optionalKeys": ["path", "maxMatches"], "riskLevel": "read", "trustedOnly": True},
        {"action": "workspace_diff", "runtime": "workspace", "requiredKeys": ["path", "content"], "optionalKeys": [], "riskLevel": "write_preview", "trustedOnly": True},
        {"action": "workspace_apply_patch", "runtime": "workspace", "requiredKeys": ["path", "content"], "optionalKeys": ["expectedSha256", "patch", "summary"], "riskLevel": "write", "trustedOnly": True},
        {"action": "workspace_run_shell", "runtime": "workspace", "requiredKeys": ["command"], "optionalKeys": ["timeoutSeconds"], "riskLevel": "shell", "trustedOnly": True},
        {"action": "mcp_call", "runtime": "mcp", "requiredKeys": ["server", "tool", "arguments"], "optionalKeys": ["url"], "riskLevel": "external_call", "trustedOnly": True},
        {"action": "mcp_http_call", "runtime": "mcp", "requiredKeys": ["url", "tool"], "optionalKeys": ["arguments", "server"], "riskLevel": "external_call", "trustedOnly": True},
        {"action": "rag_query", "runtime": "retrieval", "requiredKeys": ["query"], "optionalKeys": ["tenantId", "chatId"], "riskLevel": "read", "trustedOnly": False},
        {"action": "memory_save", "runtime": "memory", "requiredKeys": ["content"], "optionalKeys": ["tenantId", "userId", "type", "source"], "riskLevel": "write", "trustedOnly": True},
        {"action": "graph_search", "runtime": "graph", "requiredKeys": ["query"], "optionalKeys": ["tenantId", "limit"], "riskLevel": "read", "trustedOnly": False},
    ]


def evaluate_policy(request: dict[str, Any]) -> dict[str, Any]:
    action = str(request.get("action") or "")
    catalog = {item["action"]: item for item in action_catalog()}
    if action not in catalog:
        return {"allowed": False, "message": f"unknown action: {action}"}
    missing = [key for key in catalog[action]["requiredKeys"] if key not in (request.get("actionInput") or request)]
    if missing:
        return {"allowed": False, "message": "missing required keys: " + ", ".join(missing)}
    return {"allowed": True, "message": "allowed", "riskLevel": catalog[action]["riskLevel"]}


def execute_harness_action(store: PlatformStore, request: dict[str, Any]) -> dict[str, Any]:
    action = str(request.get("action") or "")
    input_data = request.get("actionInput") if isinstance(request.get("actionInput"), dict) else request
    if action == "query_school":
        return {"source": "builtin", "action": action, "observation": {"status": "success", "source": "builtin", "data": [{"name": "KnowledgeOps Campus", "city": "Online"}]}}
    if action == "query_course":
        return {"source": "builtin", "action": action, "observation": {"status": "success", "source": "builtin", "data": [{"name": "Python Rewrite", "type": input_data.get("type", "编程"), "edu": 0, "duration": 30}]}}
    if action in {"rag_query", "rag_search"}:
        return {"source": "retrieval", "action": action, "observation": retrieve(store, normalize_tenant(input_data.get("tenantId")), str(input_data.get("chatId", "")), str(input_data.get("query", "")))}
    if action == "memory_save":
        content = str(input_data.get("content", "")).strip()
        if content:
            item = {"memoryId": new_id("mem"), "tenantId": normalize_tenant(input_data.get("tenantId")), "userId": str(input_data.get("userId") or "anonymous"), "type": str(input_data.get("type") or "long"), "content": content, "confidence": 0.85, "createdAt": now_iso(), "updatedAt": now_iso()}
            store.memory_items.append(item)
            return {"source": "memory", "action": action, "observation": item}
    if action == "graph_search":
        query = str(input_data.get("query", "")).lower()
        entities = [entity for entity in store.graph_entities if query in entity["name"].lower()]
        return {"source": "graph", "action": action, "observation": {"entities": entities[:10]}}
    return {"source": "builtin", "action": action, "observation": {"status": "preview_only", "message": "Python local parity runtime did not mutate workspace"}}


def record_harness_event(store: PlatformStore, request: dict[str, Any], source: str, status_value: str, started: float, payload: dict[str, Any]) -> dict[str, Any]:
    record = {"eventId": new_id("hev"), "action": request.get("action"), "source": source, "status": status_value, "latencyMs": round((time.perf_counter() - started) * 1000, 2), "payload": payload, "createdAt": now_iso()}
    store.harness_events.append(record)
    return record


def create_workflow_task(store: PlatformStore, tenant_id: str, task_type: str, prompt: str, model_profile: Any = None, chat_id: Any = None, session_id: Any = None) -> dict[str, Any]:
    now = now_iso()
    task = {"taskId": new_id("task"), "tenantId": tenant_id, "type": task_type, "status": "DONE", "userInput": prompt, "finalOutput": f"Completed {task_type}: {prompt}", "modelProfile": model_profile or "balanced", "chatId": chat_id, "sessionId": session_id, "createdAt": now, "updatedAt": now}
    store.workflow_tasks[task["taskId"]] = task
    append_workflow_event(store, task["taskId"], "TASK_CREATED", {"type": task_type, "prompt": prompt})
    append_workflow_event(store, task["taskId"], "TASK_COMPLETED", {"output": task["finalOutput"]})
    return task


def append_workflow_event(store: PlatformStore, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    store.workflow_events.setdefault(task_id, []).append({"eventId": new_id("evt"), "taskId": task_id, "eventType": event_type, "payload": payload, "createdAt": now_iso()})


def append_memory_event(store: PlatformStore, memory_id: str, action: str, reason: str) -> None:
    store.memory_events.setdefault(memory_id, []).append({"eventId": new_id("mev"), "memoryId": memory_id, "action": action, "reason": reason, "createdAt": now_iso()})


def record_usage(store: PlatformStore, tenant_id: str, input_tokens: int, output_tokens: int) -> None:
    usage = store.usage.setdefault(tenant_id, default_usage(tenant_id))
    usage["requestCount"] += 1
    usage["inputTokens"] += input_tokens
    usage["outputTokens"] += output_tokens
    usage["totalCostUsd"] = round4(usage["totalCostUsd"] + (input_tokens * 0.000001 + output_tokens * 0.000002))
    usage["updatedAt"] = now_iso()


def default_budget(tenant_id: str) -> dict[str, Any]:
    return {"tenantId": tenant_id, "monthlyBudgetUsd": 25.0, "hardLimitEnabled": False, "updatedAt": now_iso()}


def default_usage(tenant_id: str) -> dict[str, Any]:
    return {"tenantId": tenant_id, "usageDate": now_iso()[:10], "requestCount": 0, "inputTokens": 0, "outputTokens": 0, "totalCostUsd": 0.0, "createdAt": now_iso(), "updatedAt": now_iso()}


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"tenantId", "idempotencyKey", "contentHash"}}


def route_model(profile: str, endpoint: str) -> dict[str, Any]:
    profile = profile if profile in {"cheap", "balanced", "quality"} else "balanced"
    return {"profile": profile, "model": f"local-{profile}", "reason": f"{endpoint} route resolved locally", "costTier": profile, "experimentKey": "local-parity", "experimentVariant": profile, "experimentBucket": abs(hash(f"{endpoint}:{profile}")) % 100}


def page_result(items: list[Any], page: int, page_size: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_page_size = bounded(page_size, 1, 200)
    start = (safe_page - 1) * safe_page_size
    return {"items": items[start : start + safe_page_size], "total": len(items), "page": safe_page, "pageSize": safe_page_size}


def chunk_text(text: str, size: int = 700) -> list[str]:
    clean = text.strip() or "empty document"
    return [clean[index : index + size] for index in range(0, len(clean), size)] or [clean]


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if token]


def safe_decode(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="ignore")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def build_conversation_id(history_type: str, chat_id: str) -> str:
    return f"{history_type}::{chat_id}"


def metric_inc(store: PlatformStore, name: str, amount: float = 1) -> None:
    store.metrics[name] = store.metrics.get(name, 0) + amount


def normalize_tenant(value: Any = None) -> str:
    return str(value or "public").strip() or "public"


def sha256_hex(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def epoch_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def future_iso(minutes: int = 0, days: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + minutes * 60 + days * 86400))


def bounded(value: int, lower: int, upper: int) -> int:
    return max(lower, min(int(value), upper))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(float(value), upper))


def round4(value: float) -> float:
    return round(float(value), 4)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
