# API 接入信息：base_url + 一键生成/轮换接入 key（写入 .env 的 SMARTOKEN_API_KEY）
from __future__ import annotations

import secrets

from .paths import DEV_ENV_PATH, get_env_value, set_env_value

KEY_ENV = "SMARTOKEN_API_KEY"


def generate_token() -> str:
    return "sk-smartoken-" + secrets.token_hex(12)


def get_current_key(env_path: str | None = None) -> str | None:
    return get_env_value(env_path or DEV_ENV_PATH, KEY_ENV)


def rotate_key(env_path: str | None = None) -> str:
    """生成新 key 并落盘；返回明文供一次展示。"""
    token = generate_token()
    set_env_value(env_path or DEV_ENV_PATH, KEY_ENV, token)
    return token
