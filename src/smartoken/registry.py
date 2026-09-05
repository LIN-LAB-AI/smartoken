# 模型注册表：后端池 + Ollama 自动发现 + 实时健康探测
# 设计约束：provider 是“池中成员 + 能力标签”，绝不写 if provider=="xxx" 路由分支。
from __future__ import annotations

import asyncio
import time

import httpx

from .config import Backend, Config


class BackendState:
    def __init__(self, backend: Backend):
        self.backend = backend
        self.served_models: list[str] = []      # 显式配置 + 自动发现合并
        self.healthy: bool | None = None
        self.last_probe_ts: float = 0.0
        self.last_probe_ms: int = 0

    @property
    def id(self) -> str:
        return self.backend.id


class ModelRegistry:
    """候选模型开放注册表：健康状态带 TTL 缓存，避免每请求探活。"""

    def __init__(self, config: Config):
        self.config = config
        self.states: dict[str, BackendState] = {}
        for backend in config.enabled_backends():
            self.states[backend.id] = BackendState(backend)

    # ---- 发现 ----
    async def discover(self) -> None:
        """启动期调用：Ollama 自动发现本地模型；非 ollama 后端使用显式模型清单。"""
        for state in self.states.values():
            b = state.backend
            explicit = []
            if b.extra.get("models"):
                explicit = list(b.extra["models"])
            if b.type == "ollama" and b.auto_discover:
                discovered = await self._probe_ollama_tags(b)
                state.served_models = list(dict.fromkeys(discovered + explicit))
            else:
                state.served_models = explicit
            if not state.served_models and b.default_model:
                state.served_models = [b.default_model]

    async def _probe_ollama_tags(self, backend: Backend) -> list[str]:
        url = backend.base_url.rstrip("/") + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    # ---- 健康 ----
    def _stale(self, state: BackendState) -> bool:
        ttl = state.backend.healthy_ttl_s
        return state.last_probe_ts == 0 or (time.time() - state.last_probe_ts) > ttl

    async def probe(self, state: BackendState) -> bool:
        """即时健康探测（约 1s 超时）。Ollama 探 /api/tags，其余探 /models。"""
        if not self._stale(state):
            return bool(state.healthy)
        backend = state.backend
        path = "/api/tags" if backend.type == "ollama" else "/models"
        url = backend.base_url.rstrip("/") + path
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(url)
                ok = resp.status_code < 500
        except Exception:
            ok = False
        state.healthy = ok
        state.last_probe_ts = time.time()
        state.last_probe_ms = int((time.monotonic() - start) * 1000)
        return ok

    async def refresh_health(self) -> None:
        await asyncio.gather(*(self.probe(s) for s in self.states.values()))

    # ---- 查询 ----
    def candidates(
        self,
        kinds: list[str],
        category: str = "general",
        role_mode: bool = False,
    ) -> list[BackendState]:
        """按 kind 顺序取健康且能力匹配的后端。vision 需要 vision 能力，coding 需要 coding。
        role_mode=True（策略=自定义）：仅保留 role==auto 或与任务类别匹配的后端。"""
        needed = None
        if category in ("coding", "vision"):
            needed = category
        ordered: list[BackendState] = []
        for kind in kinds:
            for state in self.states.values():
                if state.backend.kind != kind:
                    continue
                if not state.healthy and state.healthy is not None:
                    continue
                if needed and needed not in state.backend.capabilities:
                    continue
                if role_mode and not self._role_ok(state.backend.role, category):
                    continue
                ordered.append(state)
        return ordered

    @staticmethod
    def _role_ok(role: str, category: str) -> bool:
        role = (role or "auto").lower()
        if role == "auto":
            return True
        cat = category or "general"
        if cat in ("coding", "vision"):
            return role == cat
        # talking/general/agent-subtask/unknown → general 类角色（talking 视为闲聊档=general）
        return role in ("general", "talking")

    def serving(self, model_id: str) -> list[BackendState]:
        """显式 model 命中的后端（配置模型或已发现模型）。"""
        hits: list[BackendState] = []
        for state in self.states.values():
            if model_id in state.served_models or state.backend.default_model == model_id:
                hits.append(state)
        return hits

    def choose_default_model(self, state: BackendState, category: str) -> str:
        """无 default_model 时按类别启发式选已发现模型：
        coding → 优先含 coder/code；vision → 含 vision；否则取第一个。"""
        if state.backend.default_model:
            return state.backend.default_model
        pool = state.served_models or []
        if not pool:
            return ""
        if category == "coding":
            for m in pool:
                low = m.lower()
                if "coder" in low or "code" in low:
                    return m
        if category == "vision":
            for m in pool:
                if "vision" in m.lower() or "vl" in m.lower():
                    return m
        return pool[0]

    def all_models(self) -> list[dict[str, str]]:
        """模型清单。首条为虚拟路由模型 smartoken-auto：
        agent 选它时每个请求都走完整策略链（简单→本地/复杂→云端），而非钉死单一模型。"""
        out = [{"id": "smartoken-auto", "object": "model", "owned_by": "smartoken"}]
        for state in self.states.values():
            for m in state.served_models:
                out.append({"id": m, "object": "model", "owned_by": state.id})
        return out
