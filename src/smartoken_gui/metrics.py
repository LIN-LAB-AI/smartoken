# 用量聚合（纯逻辑，可单测）：读 audit/*.ndjson → 今日实时 / 历史区间统计
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any


def parse_audit_file(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                out.append(rec)
    except OSError:
        pass
    return out


def _audit_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "audit")


def _files_in_range(data_dir: str, start: date, end: date) -> list[str]:
    files: list[str] = []
    audit = _audit_dir(data_dir)
    if not os.path.isdir(audit):
        return files
    for name in os.listdir(audit):
        if not name.endswith(".ndjson"):
            continue
        stem = name[:10]
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if start <= d <= end:
            files.append(os.path.join(audit, name))
    return files


def aggregate(data_dir: str, start: date, end: date) -> dict[str, Any]:
    """按 model_id 聚合 + 按天序列。返回结构与 UI/图表共用。"""
    models: dict[str, dict[str, float]] = {}
    per_day: dict[str, dict[str, float]] = {}
    for path in _files_in_range(data_dir, start, end):
        for rec in parse_audit_file(path):
            model = rec.get("model_id") or "(unknown)"
            m = models.setdefault(model, {
                "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "cost_usd": 0.0, "flagship_usd": 0.0, "saving_usd": 0.0,
                "ttft_sum_ms": 0.0, "tps_sum": 0.0,
            })
            m["requests"] += 1
            m["prompt_tokens"] += int(rec.get("prompt_tokens", 0) or 0)
            m["completion_tokens"] += int(rec.get("completion_tokens", 0) or 0)
            m["cost_usd"] += float(rec.get("actual_cost_usd", 0.0) or 0.0)
            m["flagship_usd"] += float(rec.get("flagship_cost_usd", 0.0) or 0.0)
            m["saving_usd"] += float(rec.get("saving_usd", 0.0) or 0.0)
            m["ttft_sum_ms"] += float(rec.get("ttft_ms", 0.0) or 0.0)
            m["tps_sum"] += float(rec.get("decode_tps", 0.0) or 0.0)
            day = rec.get("ts")
            day = _day_of(day)
            if day:
                d = per_day.setdefault(day, {
                    "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "cost_usd": 0.0, "saving_usd": 0.0,
                })
                d["requests"] += 1
                d["prompt_tokens"] += int(rec.get("prompt_tokens", 0) or 0)
                d["completion_tokens"] += int(rec.get("completion_tokens", 0) or 0)
                d["cost_usd"] += float(rec.get("actual_cost_usd", 0.0) or 0.0)
                d["saving_usd"] += float(rec.get("saving_usd", 0.0) or 0.0)

    for m in models.values():
        if m["requests"]:
            m["avg_tps"] = round(m["tps_sum"] / m["requests"], 2)
            m["avg_ttft_ms"] = round(m["ttft_sum_ms"] / m["requests"], 1)
    days = sorted(per_day)
    totals = {
        "requests": sum(m["requests"] for m in models.values()),
        "prompt_tokens": sum(m["prompt_tokens"] for m in models.values()),
        "completion_tokens": sum(m["completion_tokens"] for m in models.values()),
        "cost_usd": round(sum(m["cost_usd"] for m in models.values()), 6),
        "flagship_usd": round(sum(m["flagship_usd"] for m in models.values()), 6),
        "saving_usd": round(sum(m["saving_usd"] for m in models.values()), 6),
    }
    return {
        "models": models,
        "per_day": [dict(per_day[d], date=d) for d in days],
        "totals": totals,
    }


def _day_of(epoch: Any) -> str | None:
    try:
        ts = float(epoch)
        if ts > 1e12:   # 毫秒级 → 转秒
            ts /= 1000.0
        if ts > 1e9:    # 秒级时间戳
            return date.fromtimestamp(ts).isoformat()
    except (TypeError, ValueError, OSError):
        pass
    return None


def last_n_days(n: int) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=max(n - 1, 0)), end


def read_live(data_dir: str) -> dict[str, Any]:
    path = os.path.join(data_dir, "live.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"current": None, "last": None}
