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


def _run_smoke_test() -> int:
    """Import modules that previously failed only after deployment."""
    import _sqlite3  # noqa: F401
    import sqlite3  # noqa: F401
    import uvicorn  # noqa: F401
    import app.main  # noqa: F401

    print("grok2api FreeBSD self-test ok")
    return 0


def _run_granian() -> int:
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = os.getenv("SERVER_PORT", "8000")
    workers = os.getenv("SERVER_WORKERS", "1")

    if len(sys.argv) > 1:
        sys.argv = ["granian", *sys.argv[1:]]
    else:
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


def _run_uvicorn() -> int:
    import uvicorn

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    workers = int(os.getenv("SERVER_WORKERS", "1"))
    if workers != 1:
        print("SERVER_ENGINE=uvicorn on serv00 supports SERVER_WORKERS=1; forcing workers=1")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


def main() -> int:
    _configure_runtime_paths()

    if os.getenv("GROK2API_FREEBSD_SELF_TEST") == "1" or "--self-test" in sys.argv[1:]:
        return _run_smoke_test()

    engine = os.getenv("SERVER_ENGINE", "uvicorn").strip().lower()
    if engine == "granian" or len(sys.argv) > 1:
        return _run_granian()
    if engine == "uvicorn":
        return _run_uvicorn()

    raise SystemExit(f"Unsupported SERVER_ENGINE={engine!r}; use uvicorn or granian")


if __name__ == "__main__":
    raise SystemExit(main())
