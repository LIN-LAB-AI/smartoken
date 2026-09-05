# 路径与密钥文件工具（dev 阶段项目 .env；S3 迁移到 %APPDATA%\Smartoken）
from __future__ import annotations

import os
import re

# 项目根 = 本文件上溯两级（src/smartoken_gui/../..）
GUI_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(GUI_DIR, "..", ".."))

DEV_ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# 常见配置文件名（dev 默认用 dev-china.yaml；不存在回退 router.yaml）
DEFAULT_CONFIG_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "config", "dev-china.yaml"),
    os.path.join(PROJECT_ROOT, "config", "router.yaml"),
]


def default_config_path() -> str:
    for p in DEFAULT_CONFIG_CANDIDATES:
        if os.path.exists(p):
            return p
    return DEFAULT_CONFIG_CANDIDATES[0]


# ---- .env 读写（保其他行不动）----
def get_env_value(path: str, key: str) -> str | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + "="):
                    return line[len(key) + 1:]
    except OSError:
        return None
    return None


def set_env_value(path: str, key: str, value: str) -> None:
    lines: list[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines(keepends=True)
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    found = False
    for i, line in enumerate(lines):
        if pattern.match(line.rstrip("\r\n")):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
