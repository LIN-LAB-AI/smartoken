# Smartoken 配置加载：内嵌默认 + 文件深合并 + 环境变量密钥注入
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

# 内嵌默认配置与 config/router.yaml 保持同构；文件只写覆盖项（抄 routelabs DEFAULT_CONFIG 深合并思路）
DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8787},
    "data_dir": "./data",
    "audit_retention_days": 7,
    "flagship_reference": {"id": "china-flagship-ref", "input_per_mtok_usd": 0.30, "output_per_mtok_usd": 1.20},
    "registry": {"backends": []},
    "policies": {
        "difficulty_map": {"L0": ["local"], "L1": ["local", "cloud-free"], "L2": ["cloud", "cloud-free", "local"]},
        "active_scenario": "auto",
        # 场景套餐：给 GUI 提供语义化策略档（聊天省 / coding 强）。值 = 覆盖该档的 difficulty_map。
        "scenarios": {
            "auto": {},
            "talking": {"L0": ["local"], "L1": ["local"], "L2": ["local", "cloud"]},   # 聊天尽量本地，超复杂才上云
            "coding": {"L0": ["local"], "L1": ["local", "cloud"], "L2": ["cloud", "local"]},  # 写码：简单本地，复杂给云上 coding 强模型
            "general": {"L0": ["local"], "L1": ["local", "cloud"], "L2": ["cloud", "local"]},
        },
        "classifier": {
            "l2_stacktrace_words": ["traceback", "stack trace", "segmentation fault", "crash log", "堆栈", "报错", "异常"],
            "l2_architecture_words": ["architecture", "refactor", "migration", "架构", "重构", "迁移", "模块划分", "系统设计", "代码库"],
        },
    },
    "identity_profiles": {},
    "preference": {"categories": {}},
    "budget": {"enabled": False, "cloud_daily_usd": 0.0, "max_cloud_cost_usd_per_req": 0.0},
}


@dataclass
class Backend:
    id: str
    kind: str            # local | cloud-free | cloud
    type: str            # ollama | openai_compatible（仅此两种；不做 Anthropic 协议）
    base_url: str
    enabled: bool = True
    auto_discover: bool = False
    api_key_env: str | None = None
    default_model: str = ""
    capabilities: list[str] = field(default_factory=lambda: ["general"])
    cost_per_mtok_in_usd: float = 0.0
    cost_per_mtok_out_usd: float = 0.0
    healthy_ttl_s: float = 5.0
    role: str = "auto"    # auto | coding | talking/general | vision（策略自定义模式用）
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env) or None

    @property
    def is_local(self) -> bool:
        return self.kind == "local"

    def outbound_base(self) -> str:
        """OpenAI-compatible 出站根地址。"""
        if self.type == "ollama":
            return self.base_url.rstrip("/") + "/v1"
        return self.base_url.rstrip("/")


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class Config:
    server_host: str
    server_port: int
    data_dir: str
    flagship_reference: dict[str, Any]
    backends: list[Backend]
    difficulty_map: dict[str, list[str]]
    classifier_rules: dict[str, Any]
    identity_profiles: dict[str, str]
    preferences: dict[str, list[str]]
    budget: dict[str, Any]
    active_scenario: str = "auto"
    strategy_mode: str = "auto"   # auto（全局智能） | custom（按行角色过滤）
    retention_days: int = 7
    raw: dict[str, Any] = field(default_factory=dict)

    def backend(self, backend_id: str) -> Backend | None:
        for b in self.backends:
            if b.id == backend_id:
                return b
        return None

    def enabled_backends(self) -> list[Backend]:
        return [b for b in self.backends if b.enabled]


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_config_path(cli_path: str | None) -> str | None:
    if cli_path:
        return cli_path
    env = os.environ.get("SMARTOKEN_CONFIG")
    if env:
        return env
    local = os.path.join("config", "router.yaml")
    if os.path.exists(local):
        return local
    return None


def _load_dotenv() -> None:
    """可选加载 .env（密钥只放 gitignore 的 .env，不进配置文件/仓库）。
    已有 shell 环境变量优先，不覆盖。加载失败静默 —— 无 .env 也能跑。"""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    try:
        load_dotenv(os.path.join(os.getcwd(), ".env"), override=False)
    except Exception:
        return


def load_config(cli_path: str | None = None) -> Config:
    _load_dotenv()
    raw: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
    path = resolve_config_path(cli_path)
    if path:
        raw = _deep_merge(raw, _load_yaml(path))

    data_dir = os.environ.get("SMARTOKEN_HOME") or raw["data_dir"]
    data_dir = os.path.abspath(data_dir)

    backends = [Backend(**b) for b in raw["registry"]["backends"]]
    # 场景套餐解析：active_scenario 命中 → 用该场景的 difficulty_map 覆盖默认
    active = str(raw["policies"].get("active_scenario", "auto") or "auto")
    scenarios = raw["policies"].get("scenarios", {}) or {}
    diff = raw["policies"]["difficulty_map"]
    if active in scenarios and scenarios[active]:
        diff = _deep_merge(diff, scenarios[active])
    prefs = raw["preference"]["categories"]
    profiles = raw.get("identity_profiles", {}) or {}
    return Config(
        server_host=raw["server"]["host"],
        server_port=int(raw["server"]["port"]),
        data_dir=data_dir,
        flagship_reference=raw["flagship_reference"],
        backends=backends,
        difficulty_map=diff,
        classifier_rules=raw["policies"].get("classifier", {}),
        identity_profiles=profiles,
        preferences=prefs,
        budget=raw["budget"],
        active_scenario=active,
        strategy_mode=str(raw["policies"].get("strategy_mode", "auto") or "auto"),
        retention_days=int(raw.get("audit_retention_days", 7) or 7),
        raw=raw,
    )
