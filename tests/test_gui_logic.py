"""smartoken_gui 纯逻辑单测（不依赖 Qt 显示）"""
import os

import yaml

from smartoken_gui import configfile
from smartoken_gui.api_tokens import generate_token, rotate_key
from smartoken_gui.paths import get_env_value, set_env_value


def _mk_cfg(tmp_path) -> str:
    p = tmp_path / "router.yaml"
    p.write_text(yaml.safe_dump({
        "server": {"host": "127.0.0.1", "port": 8787},
        "policies": {"active_scenario": "auto"},
        "registry": {"backends": [
            {"id": "b1", "kind": "local", "type": "openai_compatible",
             "base_url": "http://127.0.0.1:88/v1", "default_model": "m1", "enabled": True},
        ]},
    }), encoding="utf-8")
    return str(p)


def test_scenario_roundtrip(tmp_path):
    p = _mk_cfg(tmp_path)
    assert configfile.get_active_scenario(p) == "auto"
    configfile.set_active_scenario(p, "talking")
    # ruamel 或 safe 后仍可读
    assert configfile.get_active_scenario(p) == "talking"


def test_backend_toggle_preserves_other_fields(tmp_path):
    p = _mk_cfg(tmp_path)
    configfile.set_backend_enabled(p, "b1", False)
    rows = configfile.list_backends(p)
    assert rows[0]["enabled"] is False
    assert rows[0]["default_model"] == "m1"      # 其它字段未被破坏
    configfile.set_backend_enabled(p, "b1", True)
    assert configfile.list_backends(p)[0]["enabled"] is True


def test_env_value_set_and_get(tmp_path):
    env = tmp_path / ".env"
    assert get_env_value(str(env), "A") is None
    set_env_value(str(env), "A", "1")
    set_env_value(str(env), "B", "2")
    set_env_value(str(env), "A", "3")            # 覆盖
    assert get_env_value(str(env), "A") == "3"
    assert get_env_value(str(env), "B") == "2"


def test_token_generate_and_rotate(tmp_path):
    env = str(tmp_path / ".env")
    t1 = generate_token()
    assert t1.startswith("sk-smartoken-")
    t2 = rotate_key(env)
    assert get_env_value(env, "SMARTOKEN_API_KEY") == t2
    assert t2 != t1
