# 出站适配：把选定的 backend 调用出去。
# 产品决策：只做 OpenAI-compatible 一种出站协议（覆盖 Ollama /v1 与国产/兼容云端），
# 不实现任何 Anthropic 协议翻译。
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .config import Backend


def _headers(backend: Backend) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if backend.api_key:
        h["Authorization"] = f"Bearer {backend.api_key}"
    return h


async def send_chat(
    backend: Backend,
    payload: dict[str, Any],
    *,
    timeout: float = 300.0,
) -> httpx.Response:
    """整包请求（非流式场景也由本函数发出；流式见 send_chat_stream）。"""
    url = backend.outbound_base() + "/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=_headers(backend))
        resp.raise_for_status()
        return resp


async def send_chat_stream(
    backend: Backend,
    payload: dict[str, Any],
    *,
    timeout: float = 300.0,
) -> AsyncIterator[str]:
    """流式 SSE 直通：对同协议后端零改写透传（含空行分隔，保证帧边界完整）。"""
    url = backend.outbound_base() + "/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", url, json=payload, headers=_headers(backend)
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                yield line + "\n"


def extract_usage(payload: dict[str, Any]) -> tuple[int, int]:
    """从响应里抠 token 用量；流式下最后一个 chunk 才带 usage，缺省按 0 并回退估算。"""
    usage = payload.get("usage") or {}
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def usage_from_sse_chunks(chunks: list[str]) -> tuple[int, int]:
    """聚合流式 chunk：取最后一个带 usage 的 data 行。"""
    p = c = 0
    for raw in chunks:
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if "usage" in obj:
            p, c = extract_usage(obj)
    return p, c
