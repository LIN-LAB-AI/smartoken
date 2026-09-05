# 审计层：一份结构化日志喂三个用途（面板 / 轨道B学习器 / 预算回算）
# 隐私纪律：只落特征与决策元数据，绝不落 user message 原文（OpenClaw INFO 全量打印是反例）。
from __future__ import annotations

import json
import os
from datetime import date

from .config import Config
from .models import AuditRecord


class AuditStore:
    def __init__(self, config: Config):
        self.dir = os.path.join(config.data_dir, "audit")
        os.makedirs(self.dir, exist_ok=True)

    def _path_today(self) -> str:
        return os.path.join(self.dir, f"{date.today().isoformat()}.ndjson")

    def append(self, record: AuditRecord) -> None:
        with open(self._path_today(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")

    def cloud_spend_today_usd(self) -> float:
        """P5 预算闸门的数据源：今日云端实际花费（local 永远 0）。"""
        path = self._path_today()
        total = 0.0
        if not os.path.exists(path):
            return 0.0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += float(rec.get("actual_cost_usd", 0.0))
        return total


def prune_audit_dir(data_dir: str, keep_days: int) -> int:
    """7 天（可配）留存：删除 audit 目录下早于 keep_days 的 *.ndjson，返回删除数。"""
    if keep_days <= 0:
        return 0
    audit_dir = os.path.join(data_dir, "audit")
    if not os.path.isdir(audit_dir):
        return 0
    import time as _t
    cutoff = _t.time() - keep_days * 86400
    removed = 0
    for name in os.listdir(audit_dir):
        if not name.endswith(".ndjson"):
            continue
        p = os.path.join(audit_dir, name)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
                removed += 1
        except OSError:
            continue
    return removed


def estimate_usd(
    prompt_tokens: int, completion_tokens: int,
    per_mtok_in: float, per_mtok_out: float,
) -> float:
    return prompt_tokens / 1_000_000 * per_mtok_in + completion_tokens / 1_000_000 * per_mtok_out
