"""策略自定义：每行角色过滤 + configfile 增删改（GUI 配套）"""
import pytest
import yaml

from smartoken.classifier import ClassifierResult
from smartoken.config import Backend, Config, load_config
from smartoken.registry import ModelRegistry
from smartoken.router_core import RouterCore

from smartoken_gui import configfile


def _cfg(strategy_mode="auto", roles=None) -> Config:
    roles = roles or {}
    backends = [
        Backend(id="deepseek", kind="cloud", type="openai_compatible", base_url="https://ds/v1",
                default_model="deepseek-chat", capabilities=["coding", "general"],
                role=roles.get("deepseek", "auto")),
        Backend(id="local-coder", kind="local", type="openai_compatible", base_url="http://127.0.0.1:1/v1",
                default_model="coder", capabilities=["coding"], role=roles.get("local-coder", "auto")),
        Backend(id="glm", kind="cloud", type="openai_compatible", base_url="https://glm/v1",
                default_model="glm-4.5", capabilities=["general"], role=roles.get("glm", "auto")),
    ]
    return Config(
        server_host="127.0.0.1", server_port=8787, data_dir="./data",
        flagship_reference={"id": "r", "input_per_mtok_usd": 1.0, "output_per_mtok_usd": 2.0},
        backends=backends,
        difficulty_map={"L0": ["local"], "L1": ["local", "cloud"], "L2": ["cloud", "local"]},
        classifier_rules={}, identity_profiles={}, preferences={}, budget={},
        active_scenario="auto", strategy_mode=strategy_mode,
    )


def _reg(cfg, healthy):
    reg = ModelRegistry(cfg)
    for sid in reg.states:
        reg.states[sid].healthy = sid in healthy
    return reg


def _cls(category, difficulty="L1"):
    return ClassifierResult(difficulty=difficulty, category=category, confidence=0.8)


def test_auto_mode_ignores_roles():
    # 本地全挂：只剩 deepseek/glm。auto 忽略 glm 的 role=coding，general 仍按云顺序选 deepseek。
    cfg = _cfg("auto", roles={"glm": "coding"})
    reg = _reg(cfg, ["deepseek", "glm"])
    r = RouterCore(cfg, reg)
    d = r.decide(request_model=None, classification=_cls("general"))
    assert d.backend_id == "deepseek"


def test_custom_mode_filters_by_role():
    cfg = _cfg("custom", roles={"deepseek": "coding", "local-coder": "coding", "glm": "general"})
    reg = _reg(cfg, ["deepseek", "local-coder", "glm"])
    r = RouterCore(cfg, reg)
    # general(L1)：local 先；但 local-coder 角色=coding 被过滤 → 落到 cloud 的 glm(general)
    d = r.decide(request_model=None, classification=_cls("general"))
    assert d.backend_id == "glm"
    # coding(L1)：local-coder 角色=coding 且能力 coding → 本地优先命中
    d2 = r.decide(request_model=None, classification=_cls("coding"))
    assert d2.backend_id == "local-coder"


# ---- configfile 配套 ----
def _mk_cfg(tmp_path) -> str:
    p = tmp_path / "router.yaml"
    p.write_text(yaml.safe_dump({
        "policies": {"strategy_mode": "auto"},
        "registry": {"backends": [
            {"id": "b1", "kind": "local", "type": "openai_compatible",
             "base_url": "http://127.0.0.1:88/v1", "default_model": "m1", "enabled": True, "role": "auto"},
        ]},
    }), encoding="utf-8")
    return str(p)


def test_strategy_and_role_roundtrip(tmp_path):
    p = _mk_cfg(tmp_path)
    assert configfile.get_strategy_mode(p) == "auto"
    configfile.set_strategy_mode(p, "custom")
    configfile.set_backend_role(p, "b1", "coding")
    assert configfile.get_strategy_mode(p) == "custom"
    assert configfile.list_backends(p)[0]["role"] == "coding"


def test_add_remove_backend(tmp_path):
    p = _mk_cfg(tmp_path)
    configfile.add_backend(p, {"id": "b2", "kind": "cloud", "type": "openai_compatible",
                               "base_url": "https://x/v1", "default_model": "m2",
                               "api_key_env": "SMARTOKEN_X_KEY"})
    ids = [b["id"] for b in configfile.list_backends(p)]
    assert ids == ["b1", "b2"]
    with pytest.raises(ValueError):
        configfile.add_backend(p, {"id": "b2", "base_url": "http://y"})
    assert configfile.remove_backend(p, "b2") is True
    assert [b["id"] for b in configfile.list_backends(p)] == ["b1"]


def test_load_config_reads_role_and_mode(tmp_path):
    p = _mk_cfg(tmp_path)
    cfg = load_config(p)
    assert cfg.strategy_mode == "auto"
    assert cfg.backend("b1").role == "auto"
