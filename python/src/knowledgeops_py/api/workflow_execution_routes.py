"""Workflow execution and lifecycle routes backed by the application service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from knowledgeops_py.application.workflow import ReactWorkflowApplicationService, WorkflowNotResumable
from knowledgeops_py.dto import ChatRequestDto, ChatResponseDto


def register_workflow_execution_routes(
    app: FastAPI,
    *,
    store: Any,
    workflow_service: ReactWorkflowApplicationService | None,
    workflow_repository: Any,
    settings: Any,
    session_repository: Any,
    memory_service: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    tenant_context: Callable[[Any], Any],
    chat_response_with_provider: Callable[..., Awaitable[ChatResponseDto]],
    create_workflow_task: Callable[..., dict[str, Any]],
    to_sse: Callable[..., str],
    to_sse_error: Callable[..., str],
) -> None:
    """Register Java-compatible workflow execution, recovery, and cancel routes."""

    @app.post("/ai/workflow/react/chat")
    async def workflow_chat(
        payload: ChatRequestDto,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        if workflow_service is not None:

            async def respond() -> dict[str, Any]:
                response = await chat_response_with_provider(
                    store,
                    ctx,
                    payload,
                    mode="workflow",
                    require_evidence=False,
                    settings=settings,
                    session_repository=session_repository,
                    memory_service=memory_service,
                )
                return response.model_dump()

            workflow = await workflow_service.run(
                tenant_context(ctx), payload.prompt, payload.modelProfile, payload.chatId, respond
            )
            response = ChatResponseDto.model_validate(workflow.response)
            task = workflow.task
        else:
            response = await chat_response_with_provider(
                store,
                ctx,
                payload,
                mode="workflow",
                require_evidence=False,
                settings=settings,
                session_repository=session_repository,
                memory_service=memory_service,
            )
            task = create_workflow_task(store, ctx, payload, response)
        result = response.model_dump() | {"taskId": task["taskId"], "status": task["status"]}
        return ok(result, trace_id=ctx.trace_id)

    @app.post("/ai/workflow/react/chat/stream")
    async def workflow_stream(
        request: Request,
        payload: ChatRequestDto,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> PlainTextResponse:
        legacy = is_legacy_request(request)
        try:
            if workflow_service is not None:

                async def respond() -> dict[str, Any]:
                    response = await chat_response_with_provider(
                        store,
                        ctx,
                        payload,
                        mode="workflow",
                        require_evidence=False,
                        settings=settings,
                        session_repository=session_repository,
                        memory_service=memory_service,
                    )
                    return response.model_dump()

                workflow = await workflow_service.run(
                    tenant_context(ctx), payload.prompt, payload.modelProfile, payload.chatId, respond
                )
                response = ChatResponseDto.model_validate(workflow.response)
            else:
                response = await chat_response_with_provider(
                    store,
                    ctx,
                    payload,
                    mode="workflow",
                    require_evidence=False,
                    settings=settings,
                    session_repository=session_repository,
                    memory_service=memory_service,
                )
                create_workflow_task(store, ctx, payload, response)
        except Exception as exc:
            return PlainTextResponse(to_sse_error(exc, ctx.trace_id, legacy), media_type="text/event-stream")
        return PlainTextResponse(
            to_sse(response, ctx.trace_id, legacy=legacy, react=True), media_type="text/event-stream"
        )

    @app.post("/ai/workflow/tasks/{taskId}/resume")
    async def workflow_resume(
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        if not is_legacy_request(request) or workflow_service is None or workflow_repository is None:
            raise HTTPException(status_code=404, detail="task not found")
        task = await workflow_repository.get(ctx.tenant_id, taskId)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        payload = ChatRequestDto(
            chatId=str(task["chatId"]),
            prompt=str(task["userInput"]),
            modelProfile=str(task["modelProfile"]),
        )

        async def respond() -> dict[str, Any]:
            response = await chat_response_with_provider(
                store,
                ctx,
                payload,
                mode="workflow",
                require_evidence=False,
                settings=settings,
                session_repository=session_repository,
                memory_service=memory_service,
            )
            return response.model_dump()

        try:
            workflow = await workflow_service.resume(tenant_context(ctx), taskId, respond)
        except WorkflowNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = ChatResponseDto.model_validate(workflow.response)
        return ok(
            response.model_dump() | {"taskId": taskId, "status": workflow.task["status"]},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/workflow/tasks/{taskId}/cancel")
    async def workflow_cancel(
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        if not is_legacy_request(request) or workflow_service is None:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            task = await workflow_service.cancel(tenant_context(ctx), taskId)
        except WorkflowNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task, trace_id=ctx.trace_id)
