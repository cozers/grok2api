# grok2api FreeBSD/serv00 binary

This package is built on FreeBSD amd64 for serv00-style deployments.

## Files

- `grok2api`: bundled executable.
- `config.defaults.toml`: default runtime configuration.
- `.env.example`: example environment variables.

## Quick Start

```sh
chmod +x ./grok2api
mkdir -p data logs
cp .env.example .env
```

Edit `.env` as needed, then start:

```sh
set -a
. ./.env
set +a
SERVER_HOST=0.0.0.0 SERVER_PORT=8000 ./grok2api
```

The executable uses `./data` and `./logs` by default. You can override them with:

```sh
DATA_DIR="$HOME/domains/example.com/grok2api/data" \
LOG_DIR="$HOME/domains/example.com/grok2api/logs" \
SERVER_PORT=8000 \
./grok2api
```

Open `/admin/login` after startup. The default admin password is `grok2api` unless changed in configuration.
