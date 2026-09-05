# 配置文件安全编辑：用 ruamel round-trip 保注释；scenario/backends.enabled 等定点改写
from __future__ import annotations

from typing import Any

try:  # ruamel 保注释；缺失则退回 yaml.safe（丢注释，但功能可用）
    from ruamel.yaml import YAML
    _RUAMEL = True
except Exception:  # pragma: no cover
    _RUAMEL = False
    import yaml


def load(path: str) -> Any:
    if _RUAMEL:
        y = YAML(typ="rt")
        with open(path, "r", encoding="utf-8") as fh:
            return y.load(fh) or {}
    return _yaml_safe_load(path)


def save(path: str, data: Any) -> None:
    if _RUAMEL:
        y = YAML(typ="rt")
        y.width = 4096  # 少折行，配置可读
        with open(path, "w", encoding="utf-8") as fh:
            y.dump(data, fh)
        return
    _yaml_safe_dump(path, data)


def _yaml_safe_load(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _yaml_safe_dump(path: str, data: Any) -> None:
    import yaml
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def get_active_scenario(path: str) -> str:
    data = load(path)
    return str((data.get("policies", {}).get("active_scenario")) or "auto")


def set_active_scenario(path: str, scenario: str) -> None:
    data = load(path)
    data.setdefault("policies", {})["active_scenario"] = scenario
    save(path, data)


def get_strategy_mode(path: str) -> str:
    data = load(path)
    return str(data.get("policies", {}).get("strategy_mode", "auto") or "auto")


def set_strategy_mode(path: str, mode: str) -> None:
    data = load(path)
    data.setdefault("policies", {})["strategy_mode"] = mode
    save(path, data)


def set_backend_enabled(path: str, backend_id: str, enabled: bool) -> None:
    data = load(path)
    for b in data.get("registry", {}).get("backends", []):
        if b.get("id") == backend_id:
            b["enabled"] = bool(enabled)
            break
    save(path, data)


def set_backend_role(path: str, backend_id: str, role: str) -> None:
    data = load(path)
    for b in data.get("registry", {}).get("backends", []):
        if b.get("id") == backend_id:
            b["role"] = role
            break
    save(path, data)


def add_backend(path: str, cfg: dict) -> None:
    """新增后端；cfg 至少含 id/base_url/kind/type。已存在同名 id 时抛 ValueError。"""
    data = load(path)
    backends = data.setdefault("registry", {}).setdefault("backends", [])
    if any(b.get("id") == cfg.get("id") for b in backends):
        raise ValueError(f"backend id '{cfg.get('id')}' 已存在")
    entry = {
        "id": cfg["id"], "kind": cfg.get("kind", "local"),
        "type": cfg.get("type", "openai_compatible"),
        "base_url": cfg["base_url"], "enabled": True,
        "default_model": cfg.get("default_model", ""),
        "api_key_env": cfg.get("api_key_env"),
        "capabilities": cfg.get("capabilities", ["general"]),
        "cost_per_mtok_in_usd": float(cfg.get("cost_per_mtok_in_usd", 0.0)),
        "cost_per_mtok_out_usd": float(cfg.get("cost_per_mtok_out_usd", 0.0)),
        "role": cfg.get("role", "auto"),
    }
    entry = {k: v for k, v in entry.items() if v is not None}
    backends.append(entry)
    save(path, data)


def remove_backend(path: str, backend_id: str) -> bool:
    data = load(path)
    backends = data.get("registry", {}).get("backends", [])
    kept = [b for b in backends if b.get("id") != backend_id]
    if len(kept) == len(backends):
        return False
    data["registry"]["backends"] = kept
    save(path, data)
    return True


def list_backends(path: str) -> list[dict[str, Any]]:
    data = load(path)
    return [dict(b) for b in data.get("registry", {}).get("backends", [])]
