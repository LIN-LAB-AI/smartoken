# 实时快照：GUI 桌面气泡/看板轮询的唯一数据源（0.5s 粒度足够）
# 文件结构: {"current": {...}|null, "last": {...}|null}
from __future__ import annotations

import json
import os
import time
from typing import Any


class LiveStore:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "live.json")
        os.makedirs(data_dir, exist_ok=True)
        self._write({"current": None, "last": None})

    def _write(self, obj: dict[str, Any]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    def _read(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"current": None, "last": None}

    def start(
        self, request_id: str, backend_id: str, model_id: str,
        prompt_tokens_est: int, scenario: str,
    ) -> None:
        now = time.time()
        cur = {
            "request_id": request_id,
            "backend_id": backend_id,
            "model_id": model_id,
            "scenario": scenario,
            "prompt_tokens_est": prompt_tokens_est,
            "completion_tokens": 0,
            "decode_tps": 0.0,
            "started_at": now,
            "elapsed_s": 0,
        }
        data = self._read()
        data["current"] = cur
        data["last"] = None
        self._write(data)

    def finish(self, request_id: str, stats: dict[str, Any]) -> None:
        """stats: {prompt_tokens, completion_tokens, decode_tps, ttft_ms, error?}"""
        data = self._read()
        cur = data.get("current") or {}
        data["last"] = {
            "backend_id": cur.get("backend_id"),
            "model_id": cur.get("model_id"),
            "scenario": cur.get("scenario"),
            "prompt_tokens": stats.get("prompt_tokens", 0),
            "completion_tokens": stats.get("completion_tokens", 0),
            "decode_tps": round(stats.get("decode_tps", 0.0), 2),
            "ttft_ms": stats.get("ttft_ms", 0),
            "ended_at": time.time(),
            "error": stats.get("error"),
        }
        data["current"] = None
        self._write(data)
