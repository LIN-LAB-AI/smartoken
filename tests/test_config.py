"""config：深合并 + Backend 构建冒烟"""
import os

from smartoken.config import _deep_merge, load_config


def test_deep_merge_overwrites_leaf_only():
    base = {"a": {"b": 1, "c": 2}, "d": [1]}
    over = {"a": {"c": 9}}
    out = _deep_merge(base, over)
    assert out["a"]["b"] == 1
    assert out["a"]["c"] == 9
    assert out["d"] == [1]
    # 不污染原对象
    assert base["a"]["c"] == 2


def test_load_config_file_override(tmp_path, monkeypatch):
    import yaml
    cfg_path = tmp_path / "router.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "server": {"port": 9999},
        "data_dir": "./data",
        "registry": {"backends": [
            {"id": "b1", "kind": "local", "type": "ollama",
             "base_url": "http://127.0.0.1:11434", "default_model": "qwen:7b"},
        ]},
    }), encoding="utf-8")
    monkeypatch.setenv("SMARTOKEN_HOME", str(tmp_path / "home"))
    cfg = load_config(str(cfg_path))
    assert cfg.server_port == 9999
    assert cfg.server_host == "127.0.0.1"          # 来自内嵌默认
    assert cfg.backend("b1") is not None
    assert cfg.backend("b1").default_model == "qwen:7b"
    assert cfg.data_dir == os.path.abspath(str(tmp_path / "home"))
