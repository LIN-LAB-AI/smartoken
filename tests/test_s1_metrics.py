"""S1 内核增强：留存清理 / live.json / 场景套餐 / 审计新字段"""
import json
import os
import time

import yaml

from smartoken.audit import prune_audit_dir
from smartoken.config import load_config
from smartoken.live import LiveStore
from smartoken.models import AuditRecord


def test_prune_removes_only_expired(tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    old = audit / "2020-01-01.ndjson"
    new = audit / "2026-01-01.ndjson"
    old.write_text("x\n", encoding="utf-8")
    new.write_text("x\n", encoding="utf-8")
    past = time.time() - 30 * 86400
    os.utime(old, (past, past))
    removed = prune_audit_dir(str(tmp_path), keep_days=7)
    assert removed == 1
    assert not old.exists()
    assert new.exists()


def test_live_store_roundtrip(tmp_path):
    ls = LiveStore(str(tmp_path))
    ls.start("req-1", "deepseek", "deepseek-chat", 42, "coding")
    cur = json.loads((tmp_path / "live.json").read_text(encoding="utf-8"))["current"]
    assert cur["model_id"] == "deepseek-chat"
    assert cur["prompt_tokens_est"] == 42
    ls.finish("req-1", {"prompt_tokens": 100, "completion_tokens": 200, "decode_tps": 33.3, "ttft_ms": 120})
    data = json.loads((tmp_path / "live.json").read_text(encoding="utf-8"))
    assert data["current"] is None
    assert data["last"]["model_id"] == "deepseek-chat"
    assert data["last"]["decode_tps"] == 33.3


def test_active_scenario_overrides_difficulty_map(tmp_path):
    cfg_file = tmp_path / "router.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "data_dir": str(tmp_path / "data"),
        "policies": {
            "active_scenario": "talking",
            "difficulty_map": {"L0": ["local"], "L1": ["local", "cloud"], "L2": ["cloud", "local"]},
            "scenarios": {"talking": {"L0": ["local"], "L1": ["local"], "L2": ["local", "cloud"]}},
        },
    }), encoding="utf-8")
    cfg = load_config(str(cfg_file))
    assert cfg.active_scenario == "talking"
    assert cfg.difficulty_map["L1"] == ["local"]          # 被 talking 覆盖
    assert cfg.difficulty_map["L2"] == ["local", "cloud"]


def test_audit_record_new_fields_defaults():
    rec = AuditRecord(request_id="r1")
    d = rec.as_dict()
    assert d["ttft_ms"] == 0
    assert d["decode_tps"] == 0.0
    assert d["scenario"] == ""
