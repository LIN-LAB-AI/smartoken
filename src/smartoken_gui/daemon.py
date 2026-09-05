# Daemon 线程：在 QThread 内以 asyncio 跑 uvicorn（同一进程，便于打包与启停）
from __future__ import annotations

import asyncio

from PySide6.QtCore import QThread, Signal

from smartoken.config import load_config
from smartoken.registry import ModelRegistry


def _build_app(config_path: str):
    """构建 daemon app（每次启动时重新读配置，场景/开关即时生效）。"""
    from smartoken.gateway import build_app
    config = load_config(config_path)
    registry = ModelRegistry(config)
    return config, registry, build_app(config, registry)


class DaemonThread(QThread):
    """daemon 生命周期线程。start() 之后 serve() 常驻直到 stop() 置位。"""

    started = Signal(str)      # 已监听地址
    failed = Signal(str)       # 启动失败原因
    stopped = Signal(str)      # 停止原因

    def __init__(self, config_path: str, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self._server = None
        self._config = None

    @property
    def port(self) -> int:
        if self._config:
            return int(self._config.server_port)
        return 0

    @property
    def base_url(self) -> str:
        if self._config:
            host = self._config.server_host
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            return f"http://{host}:{self.port}/v1"
        return ""

    async def _serve(self) -> None:
        import uvicorn
        from smartoken.gateway import build_app

        self._config, registry, app = _build_app(self.config_path)
        await registry.discover()
        await registry.refresh_health()

        server = uvicorn.Server(uvicorn.Config(
            app, host=self._config.server_host, port=self._config.server_port,
            log_level="warning", access_log=False,
        ))
        self._server = server
        self.started.emit(f"http://{self._config.server_host}:{self._config.server_port}")
        try:
            await server.serve()
        finally:
            self._server = None

    def run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.stopped.emit("exit")

    def stop_server(self) -> None:
        server = self._server
        if server is not None:
            server.should_exit = True
