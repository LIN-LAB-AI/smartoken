# Gateway HTTP 层：只做翻译与转发决策结果，自身不含路由逻辑
#
# 产品决策（2026-09）：本产品只做 OpenAI-compatible 协议，不实现 Anthropic
# /v1/messages 与品牌接入。Claude Code 等 Anthropic 原生 agent 不在支持名单；
# 目标 agent：Cline / Cherry Studio / OpenWebUI / 自研 agent + 本地 Ollama。
from __future__ import annotations

import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .audit import AuditStore
from .config import Config
from .models import ChatCompletionRequest
from .registry import ModelRegistry
from .service import ChatService

RESPONSES_NOTE = "/v1/responses（OpenAI Responses API）透传在 M2 开放；M1 请用 /v1/chat/completions。"

_AUTH_OPEN_PATHS = {"/healthz"}


def build_app(config: Config, registry: ModelRegistry) -> FastAPI:
    service = ChatService(config, registry)
    app = FastAPI(title="Smartoken", version="0.1.0")

    # 可选静态鉴权：设置 SMARTOKEN_API_KEY 后生效（agent 用 Authorization: Bearer <key>）。
    # 不设置 = 本机直开（默认），适合仅本机使用；接外部/桌面 agent 时建议开启。
    api_key = os.environ.get("SMARTOKEN_API_KEY") or None

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if api_key is None:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _AUTH_OPEN_PATHS:
            return await call_next(request)
        if request.headers.get("authorization", "") != f"Bearer {api_key}":
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "missing or invalid bearer token"}},
            )
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        await registry.refresh_health()
        body = {}
        ok_all = True
        for sid, state in registry.states.items():
            body[sid] = {
                "healthy": bool(state.healthy),
                "kind": state.backend.kind,
                "probe_ms": state.last_probe_ms,
                "models": len(state.served_models),
            }
            ok_all = ok_all and bool(state.healthy)
        return JSONResponse({"ok": ok_all, "backends": body}, status_code=200 if ok_all else 503)

    @app.get("/v1/models")
    async def models() -> JSONResponse:
        return JSONResponse({"object": "list", "data": registry.all_models()})

    @app.post("/v1/chat/completions")
    async def chat(req: Request) -> Response:
        raw = await req.json()
        parsed = ChatCompletionRequest(**raw)
        if parsed.stream:
            gen, rec, status, err = await service.chat_stream(parsed)
            if status is not None:
                return JSONResponse(content=err or {}, status_code=status)
            assert gen is not None
            return StreamingResponse(gen, media_type="text/event-stream", headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            })
        obj, rec, status = await service.chat(parsed)
        if status is not None:
            return JSONResponse(content=obj, status_code=status)
        return JSONResponse(content=obj)

    @app.post("/v1/responses")
    async def responses() -> JSONResponse:
        return JSONResponse({"error": {"code": "not_implemented_m1", "message": RESPONSES_NOTE}}, status_code=501)

    return app
