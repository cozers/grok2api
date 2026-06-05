# grok2api FreeBSD/serv00 deployment

This package is built on FreeBSD amd64 for serv00-style deployments.

## Package Files

- `grok2api`: bundled executable.
- `start.sh`: process manager for serv00 deployment.
- `config.defaults.toml`: default runtime configuration.
- `.env.example`: example environment variables.
- `README.serv00.md`: this deployment guide.

## 1. Upload And Unpack

Upload `grok2api-freebsd-amd64.tar.gz` to your serv00 account, then unpack it:

```sh
mkdir -p ~/domains/YOUR_DOMAIN/grok2api
cd ~/domains/YOUR_DOMAIN/grok2api
tar -xzf ~/grok2api-freebsd-amd64.tar.gz --strip-components=1
chmod +x grok2api start.sh
```

Replace `YOUR_DOMAIN` with your real serv00 domain directory.

## 2. Configure

Create `.env`:

```sh
cp .env.example .env
```

Edit at least the port and public URL:

```sh
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
SERVER_WORKERS=1
SERVER_ENGINE=uvicorn
DATA_DIR=./data
LOG_DIR=./logs
LOG_FILE_ENABLED=true
```

If serv00 assigns a fixed application port, set `SERVER_PORT` to that assigned port.

`SERVER_ENGINE=uvicorn` is the default for serv00. Granian can require shared
socket operations that are blocked on some serv00 hosts, so only use
`SERVER_ENGINE=granian` when your account permits it.

## 3. Start

```sh
./start.sh start
```

Check status:

```sh
./start.sh status
```

View startup logs:

```sh
./start.sh logs
```

Stop or restart:

```sh
./start.sh stop
./start.sh restart
```

## 4. Runtime Data

By default, runtime files are stored next to the executable:

```text
./data/config.toml
./data/accounts.db
./logs/
./run/grok2api.pid
```

On first startup, `data/config.toml` is seeded from `config.defaults.toml`.

## 5. First Login

After startup, open:

```text
https://YOUR_DOMAIN/admin/login
```

The default admin password is `grok2api` unless you changed `app.app_key`.

After logging in, configure:

- `app.app_key`: admin login password.
- `app.api_key`: API key for client requests.
- `app.app_url`: your public HTTPS URL, required for media links.

## 6. Upgrade

Stop the old process, replace the binary package files, then start again:

```sh
./start.sh stop
tar -xzf ~/grok2api-freebsd-amd64.tar.gz --strip-components=1
chmod +x grok2api start.sh
./start.sh start
```

Do not delete `data/` unless you want to remove your configuration and accounts.
