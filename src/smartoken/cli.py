# CLI 入口：smartoken start [--config path]
from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from .config import load_config
from .registry import ModelRegistry

log = logging.getLogger("smartoken")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smartoken", description="Task-aware model router daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start", help="run the gateway daemon")
    p_start.add_argument(
        "--config", default=None,
        help="path to router.yaml (default: $SMARTOKEN_CONFIG or ./config/router.yaml)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "start":
        return start(args.config)
    return 2


def start(config_path: str | None) -> int:
    config = load_config(config_path)
    from .audit import prune_audit_dir
    removed = prune_audit_dir(config.data_dir, config.retention_days)
    if removed:
        log.info("audit retention: removed %d expired file(s) (keep %d days)", removed, config.retention_days)

    registry = ModelRegistry(config)

    async def bootstrap() -> None:
        await registry.discover()
        await registry.refresh_health()
        log.info("backends ready: %s", {
            s.id: {"models": len(s.served_models), "healthy": bool(s.healthy)}
            for s in registry.states.values()
        })

    asyncio.run(bootstrap())

    from .gateway import build_app
    app = build_app(config, registry)
    log.info("Smartoken listening on http://%s:%s", config.server_host, config.server_port)
    uvicorn.run(app, host=config.server_host, port=config.server_port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
