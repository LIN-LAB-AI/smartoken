# 任务分类器：T0 特征提取（纯本地、零额外调用）→ T1 规则打分
# T2（本地 few-shot 复核）M2 再接，接口已留：classify() 返回统一三元组。
from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import Category, ClassifierResult

_CODE_FENCE = re.compile(r"```|\{`\{")
_PATH_RE = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]{1,6}\b")
_IMAGE_RE = re.compile(r"data:image|image_url|\"type\":\s*\"image\"")


def hash_system_prompt(system_text: str | None) -> str:
    """agent 系统提示词指纹（P0 identity 用）。"""
    if not system_text:
        return ""
    return hashlib.sha256(system_text.encode("utf-8")).hexdigest()[:16]


def _collect_last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for seg in content:
                if isinstance(seg, dict):
                    if seg.get("type") in ("text", "input_text"):
                        parts.append(str(seg.get("text", "")))
            return "\n".join(parts)
    return ""


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 按每字 ≈1 token，ASCII 按 4 字符 ≈1 token。
    纯本地启发式，够路由分级用（中文优先的产品必须正确处理中文）。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_len = len(text) - cjk
    return max(1, cjk + ascii_len // 4)


class TaskClassifier:
    """v1 主通道：纯规则 + 阈值，延迟目标 <10ms。"""

    def __init__(self, rules: dict[str, Any] | None = None):
        self.rules = rules or {}

    def classify(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ClassifierResult:
        features = self._extract(messages, tools=tools, system_prompt=system_prompt)
        diff, conf = self._score(features)
        cat = self._category(features)
        return ClassifierResult(difficulty=diff, category=cat, confidence=conf, features=features)

    # ---- T0 ----
    def _extract(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        text = _collect_last_user_text(messages)
        has_code = bool(_CODE_FENCE.search(text))
        has_image = bool(_IMAGE_RE.search(text))
        n_paths = len(_PATH_RE.findall(text)) if text else 0
        tokens = _estimate_tokens(text)
        has_tools = bool(tools)
        sys_fp = hash_system_prompt(system_prompt)
        low = text.lower() if text else ""
        words = self.rules.get("l2_stacktrace_words", ["traceback", "stack trace"])
        arch_words = self.rules.get("l2_architecture_words", ["architecture"])
        is_stacktrace = any(w in low for w in words)
        is_architectural = any(w in low for w in arch_words)
        return {
            "last_user_len": len(text),
            "est_tokens": tokens,
            "n_messages": len(messages),
            "has_code": has_code,
            "has_image": has_image,
            "n_paths": n_paths,
            "has_tools": has_tools,
            "system_fp": sys_fp,
            "is_stacktrace": is_stacktrace,
            "is_architectural": is_architectural,
        }

    # ---- T1 ----
    def _score(self, f: dict[str, Any]) -> tuple[str, float]:
        t = f["est_tokens"]
        # L2 强信号：堆栈调试 / 架构级重构 / 超长代码任务
        if f["is_stacktrace"]:
            return "L2", 0.9
        if f["is_architectural"] or (f["has_code"] and t > 3000):
            return "L2", 0.85
        # L0 弱信号：问候/短句/无代码无工具
        if t <= 8 and not f["has_code"] and not f["has_tools"] and not f["has_image"]:
            return "L0", 0.95
        if t <= 40 and not f["has_code"] and not f["has_image"]:
            return "L0", 0.8
        # L1 缺省：带代码的普通编辑 / 有工具调用 / 中等长度
        if f["has_tools"] or f["has_code"] or 40 < t <= 3000:
            return "L1", 0.7
        return "L1", 0.55

    def _category(self, f: dict[str, Any]) -> Category:
        if f["has_image"]:
            return "vision"
        if f["has_tools"]:
            return "agent-subtask"
        if f["has_code"] or f["n_paths"] >= 2:
            return "coding"
        return "general"
