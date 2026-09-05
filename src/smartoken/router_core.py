# 路由决策引擎：六优先级策略链，自上而下短路
#   P0 identity → P1 explicit → P2 preference → P3 difficulty → P4 availability → P5 budget
# 说明：P4 不是独立步骤，而是 P0-P3 各步“选后端”时的可用性过滤（只挑健康成员），
#       由 registry.candidates()/serving() 的 healthy 过滤承载。
from __future__ import annotations

import time
from typing import Any

from .config import Config
from .models import RouteDecision
from .registry import ModelRegistry

_AUTO_MODELS = {"auto", "", "smartoken-auto"}


class RouterCore:
    def __init__(self, config: Config, registry: ModelRegistry):
        self.config = config
        self.registry = registry

    # ---- 入口 ----
    def decide(
        self,
        *,
        request_model: str | None,
        classification: Any,
        system_fp: str = "",
    ) -> RouteDecision:
        path: list[str] = []

        # P1 explicit —— 在 P0 之前判断更快且语义独立；用户显式指定优先于一切自动策略
        if request_model and request_model not in _AUTO_MODELS:
            path.append("P1 explicit")
            decision = self._decide_explicit(request_model, path)
            if decision is not None:
                return decision
            # 显式 model 无人可服务 → 明确报错，绝不静默改道
            return RouteDecision(
                backend_id="", model_id=request_model, reason="P1 explicit",
                decision_path=path,
                error=f"model '{request_model}' is not served by any enabled backend; see /v1/models",
            )

        # P0 identity：agent 指纹 → 指定后端
        if system_fp:
            pinned = self.config.identity_profiles.get(system_fp)
            if pinned:
                path.append("P0 identity")
                return self._pick(
                    backend_ids=[pinned], model_id="",
                    reason="P0 identity", path=path,
                    classification=classification,
                )

        # P2 preference：用户偏好表 category → [backend...]
        pref = self.config.preferences.get(classification.category or "general")
        if pref:
            path.append("P2 preference")
            decision = self._pick(
                backend_ids=list(pref), model_id="",
                reason="P2 preference", path=path, classification=classification,
            )
            if decision is not None and not decision.error:
                return decision

        # P3 difficulty：难度 → kind 顺序取健康候选
        diff = classification.difficulty if classification else "L1"
        kinds = self.config.difficulty_map.get(diff, ["local"])
        path.append(f"P3 difficulty [{diff}]")
        decision = self._pick(
            backend_ids=None, kinds=kinds, model_id="",
            reason=f"P3 difficulty ({diff})", path=path, classification=classification,
        )
        return decision

    # ---- 各步实现 ----
    def _decide_explicit(self, model_id: str, path: list[str]) -> RouteDecision | None:
        states = self.registry.serving(model_id)
        if not states:
            return None
        chosen = next((s for s in states if s.healthy is not False), states[0])
        return RouteDecision(
            backend_id=chosen.id, model_id=model_id,
            reason="P1 explicit", decision_path=path,
        )

    def _pick(
        self,
        *,
        backend_ids: list[str] | None,
        kinds: list[str] | None,
        model_id: str,
        reason: str,
        path: list[str],
        classification: Any,
    ) -> RouteDecision:
        cat = getattr(classification, "category", "general")
        role_mode = self.config.strategy_mode == "custom"
        states = []
        if backend_ids:
            for bid in backend_ids:
                state = self.registry.states.get(bid)
                if state and state.healthy is not False:
                    states.append(state)
        else:
            states = self.registry.candidates(kinds or ["local"], category=cat, role_mode=role_mode)

        if not states:
            return RouteDecision(
                backend_id="", model_id=model_id, reason=reason,
                decision_path=path,
                error="no healthy backend for this route",
            )
        # 同 kind 内按配置顺序选第一个健康者
        chosen = states[0]
        final_model = model_id or self.registry.choose_default_model(chosen, cat)
        if not final_model:
            return RouteDecision(
                backend_id=chosen.id, model_id="", reason=reason,
                decision_path=path,
                error=f"backend '{chosen.id}' has no routable model; add default_model or enable discovery",
            )
        return RouteDecision(
            backend_id=chosen.id, model_id=final_model,
            reason=reason, decision_path=path,
        )

    # ---- P5 budget：预算闸门（调用方在发请求前检查）----
    def budget_blocked(self, cloud_cost_today_usd: float) -> bool:
        b = self.config.budget
        if not b.get("enabled"):
            return False
        daily = float(b.get("cloud_daily_usd", 0.0))
        return daily > 0 and cloud_cost_today_usd >= daily
