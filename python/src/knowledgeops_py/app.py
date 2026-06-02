from __future__ import annotations

import hashlib
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .config import Settings, load_settings


class AuthTokenResponse(BaseModel):
    ok: int
    msg: str
    token: str | None = None
    refreshToken: str | None = None
    tenantId: str | None = None
    expiresInSeconds: int | None = None
    refreshWillExpireSoon: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    app = FastAPI(
        title="KnowledgeOps Agent Python Rewrite",
        version="0.1.0",
        docs_url="/swagger-ui/index.html",
        redoc_url=None,
    )
    app.state.settings = active_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/actuator/health")
    def health() -> dict[str, str]:
        return {"status": "UP"}

    @app.get("/actuator/prometheus")
    def prometheus() -> PlainTextResponse:
        body = "\n".join(
            [
                "# HELP knowledgeops_python_up Python rewrite liveness.",
                "# TYPE knowledgeops_python_up gauge",
                "knowledgeops_python_up 1",
                "",
            ]
        )
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.post("/auth/token", response_model=AuthTokenResponse)
    def token(
        x_api_key: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> AuthTokenResponse:
        if x_api_key != active_settings.demo_api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

        tenant_id = x_tenant_id or active_settings.demo_tenant_id
        access_token = _stable_token("access", tenant_id, active_settings)
        refresh_token = _stable_token("refresh", tenant_id, active_settings)
        return AuthTokenResponse(
            ok=1,
            msg="ok",
            token=access_token,
            refreshToken=refresh_token,
            tenantId=tenant_id,
            expiresInSeconds=active_settings.token_ttl_seconds,
        )

    @app.api_route("/ai/service", methods=["GET", "POST"], response_class=PlainTextResponse)
    async def service(
        request: Request,
        prompt: str = Query(default=""),
        chatId: str = Query(default=""),
        modelProfile: str | None = Query(default=None),
    ) -> str:
        body = await _json_body(request)
        effective_prompt = prompt or str(body.get("prompt") or "")
        effective_chat_id = chatId or str(body.get("chatId") or "")
        profile = modelProfile or body.get("modelProfile") or "balanced"
        if not effective_prompt:
            return "Python KnowledgeOps service is ready."
        chat_suffix = f" chatId={effective_chat_id}" if effective_chat_id else ""
        return f"[python:{profile}] {effective_prompt}{chat_suffix}"

    return app


def _stable_token(kind: str, tenant_id: str, settings: Settings) -> str:
    digest = hashlib.sha256(f"{kind}:{tenant_id}:{settings.demo_api_key}".encode("utf-8")).hexdigest()
    return f"py-{kind}-{digest[:32]}"


async def _json_body(request: Request) -> dict[str, Any]:
    if request.method != "POST":
        return {}
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
