"""PyInstaller launcher for the FreeBSD/serv00 build."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_env(name: str, path: Path) -> None:
    if not os.getenv(name):
        os.environ[name] = str(path)


def _configure_runtime_paths() -> None:
    workdir = Path.cwd()
    _default_env("DATA_DIR", workdir / "data")
    _default_env("LOG_DIR", workdir / "logs")
    Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["LOG_DIR"]).mkdir(parents=True, exist_ok=True)


def main() -> int:
    _configure_runtime_paths()

    if len(sys.argv) > 1:
        sys.argv = ["granian", *sys.argv[1:]]
    else:
        host = os.getenv("SERVER_HOST", "0.0.0.0")
        port = os.getenv("SERVER_PORT", "8000")
        workers = os.getenv("SERVER_WORKERS", "1")

        sys.argv = [
            "granian",
            "--interface",
            "asgi",
            "--host",
            host,
            "--port",
            port,
            "--workers",
            workers,
            "app.main:app",
        ]

    from granian.cli import entrypoint as granian_main

    result = granian_main()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
