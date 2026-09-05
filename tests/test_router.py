"""router_core：策略链（显式 / 难度 / 无健康后端 / budget 闸门）"""
import pytest

from smartoken.classifier import TaskClassifier
from smartoken.config import Backend, Config
from smartoken.models import ClassifierResult
from smartoken.registry import ModelRegistry
from smartoken.router_core import RouterCore


def _cfg(budget_enabled=False) -> Config:
    backends = [
        Backend(id="local1", kind="local", type="ollama", base_url="http://127.0.0.1:11434",
                default_model="qwen:7b", capabilities=["coding", "general"]),
        Backend(id="local2", kind="local", type="ollama", base_url="http://127.0.0.1:11435",
                default_model="llama:8b", capabilities=["general"]),
        Backend(id="cloud1", kind="cloud", type="openai_compatible", base_url="https://x/v1",
                api_key_env="SMARTOKEN_TEST_KEY", default_model="flagship", capabilities=["coding", "general"]),
    ]
    return Config(
        server_host="127.0.0.1", server_port=8787, data_dir="./data",
        flagship_reference={"id": "ref", "input_per_mtok_usd": 1.0, "output_per_mtok_usd": 2.0},
        backends=backends,
        difficulty_map={"L0": ["local"], "L1": ["local", "cloud"], "L2": ["cloud", "local"]},
        classifier_rules={}, identity_profiles={}, preferences={},
        budget={"enabled": budget_enabled, "cloud_daily_usd": 1.0, "max_cloud_cost_usd_per_req": 0.1},
        raw={},
    )


def _reg(cfg, healthy_ids) -> ModelRegistry:
    reg = ModelRegistry(cfg)
    for sid in reg.states:
        reg.states[sid].healthy = sid in healthy_ids
    return reg


def _cls(difficulty="L1", category="coding"):
    return ClassifierResult(difficulty=difficulty, category=category, confidence=0.8)


def test_explicit_model_short_circuits(monkeypatch):
    cfg = _cfg()
    reg = _reg(cfg, ["local1", "local2", "cloud1"])
    reg.states["local1"].served_models = ["qwen:7b"]
    reg.states["cloud1"].served_models = ["flagship"]
    router = RouterCore(cfg, reg)
    d = router.decide(request_model="flagship", classification=_cls())
    assert d.backend_id == "cloud1"
    assert d.model_id == "flagship"
    assert d.decision_path == ["P1 explicit"]


def test_explicit_unserved_is_error():
    cfg = _cfg()
    reg = _reg(cfg, ["local1", "cloud1"])
    router = RouterCore(cfg, reg)
    d = router.decide(request_model="nope-not-served", classification=_cls())
    assert d.error is not None and "not served" in d.error


def test_difficulty_l0_prefers_local():
    cfg = _cfg()
    reg = _reg(cfg, ["local1", "local2", "cloud1"])
    router = RouterCore(cfg, reg)
    d = router.decide(request_model=None, classification=_cls("L0", "coding"))
    assert d.backend_id == "local1"
    assert d.model_id == "qwen:7b"
    assert d.reason.startswith("P3 difficulty")


def test_difficulty_l2_prefers_cloud_when_healthy():
    cfg = _cfg()
    reg = _reg(cfg, ["local1", "cloud1"])     # cloud1 healthy
    router = RouterCore(cfg, reg)
    d = router.decide(request_model=None, classification=_cls("L2", "coding"))
    assert d.backend_id == "cloud1"


def test_all_down_gives_no_route():
    cfg = _cfg()
    reg = _reg(cfg, [])                        # 没有任何健康后端
    router = RouterCore(cfg, reg)
    d = router.decide(request_model=None, classification=_cls("L0"))
    assert d.error is not None and "no healthy backend" in d.error


def test_budget_gate():
    cfg = _cfg(budget_enabled=True)
    reg = _reg(cfg, ["local1"])
    router = RouterCore(cfg, reg)
    assert router.budget_blocked(cloud_cost_today_usd=0.5) is False
    assert router.budget_blocked(cloud_cost_today_usd=2.0) is True
