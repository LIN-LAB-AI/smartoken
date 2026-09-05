"""gateway：可选静态鉴权（SMARTOKEN_API_KEY 设置与否）+ 虚拟路由模型暴露"""
import os

from fastapi.testclient import TestClient

from smartoken.config import load_config
from smartoken.gateway import build_app
from smartoken.registry import ModelRegistry


def _app():
    cfg = load_config(None)          # 用默认/本地 router.yaml（若存在）构建纯内存 app
    return build_app(cfg, ModelRegistry(cfg))


def test_no_key_set_means_open(monkeypatch):
    monkeypatch.delenv("SMARTOKEN_API_KEY", raising=False)
    client = TestClient(_app())
    assert client.get("/v1/models").status_code == 200


def test_key_required_when_set(monkeypatch):
    monkeypatch.setenv("SMARTOKEN_API_KEY", "test-secret-123")
    client = TestClient(_app())
    r_deny = client.get("/v1/models")
    assert r_deny.status_code == 401
    r_ok = client.get("/v1/models", headers={"Authorization": "Bearer test-secret-123"})
    assert r_ok.status_code == 200
    # healthz 保持开放（运维探活）
    assert client.get("/healthz").status_code in (200, 503)


def test_models_list_exposes_smartoken_auto(monkeypatch):
    monkeypatch.delenv("SMARTOKEN_API_KEY", raising=False)
    client = TestClient(_app())
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids[0] == "smartoken-auto"
