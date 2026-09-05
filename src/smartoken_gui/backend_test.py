# 行级“测试”按钮：直接对该后端做连通探测（不依赖 daemon 是否运行）
from __future__ import annotations

import time

import httpx

from smartoken.config import Backend


def probe_backend(backend: Backend, timeout: float = 3.0) -> tuple[bool, int]:
    """返回 (连通?, 耗时 ms)。路径按后端类型：ollama→/api/tags，其余→/models（OpenAI 兼容根）。"""
    path = "/api/tags" if backend.type == "ollama" else "/models"
    url = backend.base_url.rstrip("/") + path
    headers = {}
    if backend.api_key:
        headers["Authorization"] = f"Bearer {backend.api_key}"
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        ok = resp.status_code < 500
    except Exception:
        ok = False
    return ok, int((time.monotonic() - start) * 1000)


def probe_all(config_path: str) -> dict[str, tuple[bool, int]]:
    """便捷：一次性探测配置文件里所有后端（GUI 刷新灯用）。"""
    from smartoken.config import load_config
    cfg = load_config(config_path)
    out: dict[str, tuple[bool, int]] = {}
    for b in cfg.backends:
        out[b.id] = probe_backend(b)
    return out
