# Smartoken 运行时对象模型
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Difficulty = Literal["L0", "L1", "L2"]
Category = Literal["coding", "vision", "general", "agent-subtask", "unknown"]
BackendKind = Literal["local", "cloud-free", "cloud"]
BackendType = Literal["ollama", "openai_compatible"]


class ChatCompletionRequest(BaseModel):
    """OpenAI 兼容入口的请求子集校验。

    extra="allow": agent 可能携带 thinking / reasoning_effort 等新参数，
    一律原样透传给后端，绝不在网关层截断。
    """

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[dict[str, Any]]
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class ClassifierResult:
    difficulty: Difficulty = "L1"
    category: Category = "general"
    confidence: float = 0.5
    features: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "difficulty": self.difficulty,
            "category": self.category,
            "confidence": self.confidence,
            "features": self.features,
        }


@dataclass
class RouteDecision:
    backend_id: str
    model_id: str
    reason: str                    # "P1 explicit" / "P0 identity" / ...
    decision_path: list[str] = field(default_factory=list)
    budget_exceeded: bool = False
    error: str | None = None


class AuditStatus(str, Enum):
    OK = "ok"
    FALLBACK = "fallback"
    ERROR = "error"
    BLOCKED = "blocked"            # 预算 402


@dataclass
class AuditRecord:
    ts: float = field(default_factory=time.time)
    request_id: str = ""
    features: dict[str, Any] = field(default_factory=dict)
    classification: dict[str, Any] = field(default_factory=dict)
    decision_path: list[str] = field(default_factory=list)
    reason: str = ""
    backend_id: str = ""
    model_id: str = ""
    status: AuditStatus = AuditStatus.OK
    prompt_tokens: int = 0
    completion_tokens: int = 0
    actual_cost_usd: float = 0.0
    flagship_cost_usd: float = 0.0
    saving_usd: float = 0.0
    latency_ms: int = 0
    ttft_ms: int = 0              # 首 token 时延（仅流式有意义）
    decode_tps: float = 0.0       # 解码速度 tokens/s（流式实测；非流式为估算）
    scenario: str = ""            # 命中的策略场景（auto/coding/talking/general…）
    error: str | None = None
    attempts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = self.as_dict_impl()
        return d

    def as_dict_impl(self) -> dict[str, Any]:
        return {
            "ts": round(self.ts, 3),
            "request_id": self.request_id,
            "features": self.features,
            "classification": self.classification,
            "decision_path": self.decision_path,
            "reason": self.reason,
            "backend_id": self.backend_id,
            "model_id": self.model_id,
            "status": self.status.value,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "actual_cost_usd": round(self.actual_cost_usd, 6),
            "flagship_cost_usd": round(self.flagship_cost_usd, 6),
            "saving_usd": round(self.saving_usd, 6),
            "latency_ms": self.latency_ms,
            "ttft_ms": self.ttft_ms,
            "decode_tps": round(self.decode_tps, 2),
            "scenario": self.scenario,
            "error": self.error,
            "attempts": self.attempts,
        }
