# 服务编排：Gateway 收到请求 → 分类 → 决策 → 出站（含 fallback 与预算闸门）→ 审计落盘
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from . import adapters
from .audit import AuditStore, estimate_usd
from .classifier import TaskClassifier, hash_system_prompt
from .config import Config
from .live import LiveStore
from .models import AuditRecord, AuditStatus, ChatCompletionRequest, ClassifierResult, RouteDecision
from .registry import ModelRegistry
from .router_core import RouterCore


class ChatService:
    def __init__(self, config: Config, registry: ModelRegistry):
        self.config = config
        self.registry = registry
        self.classifier = TaskClassifier(config.classifier_rules)
        self.router = RouterCore(config, registry)
        self.audit = AuditStore(config)
        self.live = LiveStore(config.data_dir)

    # ---- 决策上下文 ----
    def _system_prompt(self, messages: list[dict[str, Any]]) -> str:
        for msg in messages:
            if msg.get("role") == "system":
                return str(msg.get("content", ""))
        return ""

    # ---- 非流式主链路 ----
    async def chat(self, req: ChatCompletionRequest) -> tuple[dict[str, Any], AuditRecord, int | None]:
        request_id = uuid.uuid4().hex[:12]
        classification = self.classifier.classify(
            req.messages, tools=req.tools,
            system_prompt=self._system_prompt(req.messages),
        )
        system_fp = hash_system_prompt(self._system_prompt(req.messages))

        if self.router.budget_blocked(self.audit.cloud_spend_today_usd()):
            rec = AuditRecord(
                request_id=request_id,
                features=classification.features,
                classification=classification.as_dict(),
                status=AuditStatus.BLOCKED,
                reason="P5 budget",
                backend_id="", model_id=req.model or "",
            )
            self.audit.append(rec)
            return {"error": {"code": "budget_exceeded", "message": "cloud daily budget reached"}}, rec, 402

        decision = self.router.decide(
            request_model=req.model,
            classification=classification,
            system_fp=system_fp,
        )
        rec = AuditRecord(
            request_id=request_id,
            features=classification.features,
            classification=classification.as_dict(),
            decision_path=decision.decision_path,
            reason=decision.reason,
            backend_id=decision.backend_id,
            model_id=decision.model_id,
            error=decision.error,
        )
        rec.scenario = self.config.active_scenario
        if decision.error:
            rec.status = AuditStatus.ERROR
            self.audit.append(rec)
            return {"error": {"code": "no_route", "message": decision.error}}, rec, (400 if decision.backend_id == "" and "not served" in (decision.error or "") else 502)

        start = time.monotonic()
        payload = self._build_payload(req, decision)
        attempts: list[str] = []
        backend = self.config.backend(decision.backend_id)
        assert backend is not None
        self.live.start(
            request_id, decision.backend_id, decision.model_id,
            int(classification.features.get("est_tokens", 0)), self.config.active_scenario,
        )
        try:
            resp = await self._execute_with_fallback(payload, decision, classification, attempts)
            obj = resp.json()
            prompt_t, comp_t = adapters.extract_usage(obj)
        except httpx.HTTPError as exc:
            rec.status = AuditStatus.ERROR
            rec.error = f"all backends failed: {exc}"
            rec.attempts = attempts
            rec.latency_ms = int((time.monotonic() - start) * 1000)
            self.audit.append(rec)
            self.live.finish(request_id, {"prompt_tokens": 0, "completion_tokens": 0, "decode_tps": 0.0, "ttft_ms": 0, "error": str(exc)})
            return {"error": {"code": "upstream_error", "message": str(exc)}}, rec, 502

        rec.latency_ms = int((time.monotonic() - start) * 1000)
        rec.prompt_tokens, rec.completion_tokens = prompt_t, comp_t
        # 非流式无独立解码窗口：decode_tps 按 完成tokens/总时延 估算（GUI 标记为估算）
        if rec.latency_ms > 0 and comp_t > 0:
            rec.decode_tps = round(comp_t / (rec.latency_ms / 1000.0), 2)
        self._cost(rec, classification)
        rec.status = AuditStatus.FALLBACK if len(attempts) > 1 else AuditStatus.OK
        rec.attempts = attempts
        self.audit.append(rec)
        self.live.finish(request_id, {
            "prompt_tokens": prompt_t, "completion_tokens": comp_t,
            "decode_tps": rec.decode_tps, "ttft_ms": rec.ttft_ms,
        })
        return obj, rec, None

    async def _execute_with_fallback(
        self,
        payload: dict[str, Any],
        decision: RouteDecision,
        classification: ClassifierResult,
        attempts: list[str],
    ) -> httpx.Response:
        """候选按决策给的后端起，同类次优兜底（仅 local↔cloud-free 同 kind 池内尝试，
        绝不跨隐私边界——cloud 端失败不会把任务丢回 local 之外的非隐私后端）。"""
        state = self.registry.states[decision.backend_id]
        candidates = [state]
        for s in self.registry.states.values():
            if s.id != state.id and s.backend.kind == state.backend.kind and s.healthy is not False:
                candidates.append(s)
        last: httpx.HTTPError | None = None
        for s in candidates:
            attempts.append(s.id)
            try:
                backend = s.backend
                if payload.get("stream"):
                    raise AssertionError("stream handled by chat_stream()")
                return await adapters.send_chat(backend, payload)
            except httpx.HTTPError as exc:
                last = exc
                continue
        assert last is not None
        raise last

    # ---- 流式主链路 ----
    # 返回 (gen | None, rec, status, err_body)：status 非空表示前置错误（走 JSON 响应）。
    async def chat_stream(
        self, req: ChatCompletionRequest,
    ) -> tuple[AsyncIterator[str] | None, AuditRecord, int | None, dict[str, Any] | None]:
        request_id = uuid.uuid4().hex[:12]
        classification = self.classifier.classify(
            req.messages, tools=req.tools,
            system_prompt=self._system_prompt(req.messages),
        )
        system_fp = hash_system_prompt(self._system_prompt(req.messages))

        if self.router.budget_blocked(self.audit.cloud_spend_today_usd()):
            rec = AuditRecord(
                request_id=request_id, status=AuditStatus.BLOCKED,
                features=classification.features,
                classification=classification.as_dict(),
                reason="P5 budget", model_id=req.model or "",
            )
            self.audit.append(rec)
            return None, rec, 402, {"error": {"code": "budget_exceeded", "message": "cloud daily budget reached"}}

        decision = self.router.decide(
            request_model=req.model, classification=classification, system_fp=system_fp,
        )
        rec = AuditRecord(
            request_id=request_id,
            features=classification.features,
            classification=classification.as_dict(),
            decision_path=decision.decision_path,
            reason=decision.reason,
            backend_id=decision.backend_id,
            model_id=decision.model_id,
            error=decision.error,
        )
        rec.scenario = self.config.active_scenario
        if decision.error:
            rec.status = AuditStatus.ERROR
            self.audit.append(rec)
            status = 400 if "not served" in decision.error else 502
            return None, rec, status, {"error": {"code": "no_route", "message": decision.error}}

        backend = self.config.backend(decision.backend_id)
        assert backend is not None
        payload = self._build_payload(req, decision)
        self.live.start(
            request_id, decision.backend_id, decision.model_id,
            int(classification.features.get("est_tokens", 0)), self.config.active_scenario,
        )

        async def gen() -> AsyncIterator[str]:
            start = time.monotonic()
            first_data_ts: float | None = None
            chunks: list[str] = []
            error: str | None = None
            try:
                async for line in adapters.send_chat_stream(backend, payload):
                    if first_data_ts is None and line.startswith("data:"):
                        first_data_ts = time.monotonic()
                    chunks.append(line)
                    yield line
            except httpx.HTTPError as exc:
                error = str(exc)
                yield f'data: {{"error":{{"code":"upstream_error","message":"{error}"}}}}\n\n'
            finally:
                end = time.monotonic()
                rec.latency_ms = int((end - start) * 1000)
                if first_data_ts is not None:
                    rec.ttft_ms = int((first_data_ts - start) * 1000)
                if error is not None:
                    rec.status = AuditStatus.ERROR
                    rec.error = error
                else:
                    rec.prompt_tokens, rec.completion_tokens = adapters.usage_from_sse_chunks(chunks)
                    if first_data_ts is not None and rec.completion_tokens > 0:
                        decode_s = end - first_data_ts
                        if decode_s > 0.001:
                            rec.decode_tps = round(rec.completion_tokens / decode_s, 2)
                    self._cost(rec, classification)
                self.audit.append(rec)
                self.live.finish(request_id, {
                    "prompt_tokens": rec.prompt_tokens,
                    "completion_tokens": rec.completion_tokens,
                    "decode_tps": rec.decode_tps,
                    "ttft_ms": rec.ttft_ms,
                    "error": error,
                })

        return gen(), rec, None, None

    # ---- 公共 ----
    def _build_payload(self, req: ChatCompletionRequest, decision: RouteDecision) -> dict[str, Any]:
        """深拷贝请求体 → 仅改写 model 字段为路由结果；其余参数原样透传。"""
        import copy
        payload = copy.deepcopy(req.model_dump(exclude_none=False))
        payload["model"] = decision.model_id
        return payload

    def _cost(self, rec: AuditRecord, classification: ClassifierResult) -> None:
        backend = self.config.backend(rec.backend_id)
        in_rate = out_rate = 0.0
        if backend is not None:
            in_rate = backend.cost_per_mtok_in_usd
            out_rate = backend.cost_per_mtok_out_usd
        rec.actual_cost_usd = estimate_usd(rec.prompt_tokens, rec.completion_tokens, in_rate, out_rate)
        ref = self.config.flagship_reference
        rec.flagship_cost_usd = estimate_usd(
            rec.prompt_tokens, rec.completion_tokens,
            float(ref.get("input_per_mtok_usd", 0)), float(ref.get("output_per_mtok_usd", 0)),
        )
        rec.saving_usd = max(0.0, rec.flagship_cost_usd - rec.actual_cost_usd)
