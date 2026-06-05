#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
BIN="$APP_DIR/grok2api"
ENV_FILE="$APP_DIR/.env"
RUN_DIR="$APP_DIR/run"
PID_FILE="$RUN_DIR/grok2api.pid"
OUT_LOG="$APP_DIR/logs/grok2api.out.log"

mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$RUN_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${SERVER_HOST:=0.0.0.0}"
: "${SERVER_PORT:=8000}"
: "${SERVER_WORKERS:=1}"
: "${SERVER_ENGINE:=uvicorn}"
: "${DATA_DIR:=$APP_DIR/data}"
: "${LOG_DIR:=$APP_DIR/logs}"
: "${LOG_FILE_ENABLED:=true}"

case "$DATA_DIR" in
  /*) ;;
  *) DATA_DIR="$APP_DIR/$DATA_DIR" ;;
esac

case "$LOG_DIR" in
  /*) ;;
  *) LOG_DIR="$APP_DIR/$LOG_DIR" ;;
esac

mkdir -p "$DATA_DIR" "$LOG_DIR"

export SERVER_HOST SERVER_PORT SERVER_WORKERS SERVER_ENGINE DATA_DIR LOG_DIR LOG_FILE_ENABLED

is_running() {
  [ -f "$PID_FILE" ] || return 1
  pid=$(cat "$PID_FILE")
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

start() {
  if is_running; then
    echo "grok2api is already running: pid $(cat "$PID_FILE")"
    return 0
  fi

  chmod +x "$BIN"
  cd "$APP_DIR"
  nohup "$BIN" >> "$OUT_LOG" 2>&1 &
  echo $! > "$PID_FILE"
  echo "grok2api started: pid $(cat "$PID_FILE"), engine $SERVER_ENGINE, port $SERVER_PORT"
  echo "log: $OUT_LOG"
}

stop() {
  if ! is_running; then
    echo "grok2api is not running"
    rm -f "$PID_FILE"
    return 0
  fi

  pid=$(cat "$PID_FILE")
  kill "$pid"
  i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      kill -9 "$pid" 2>/dev/null || true
      break
    fi
    sleep 1
  done
  rm -f "$PID_FILE"
  echo "grok2api stopped"
}

status() {
  if is_running; then
    echo "grok2api is running: pid $(cat "$PID_FILE"), port $SERVER_PORT"
  else
    echo "grok2api is not running"
  fi
}

case "${1:-start}" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    start
    ;;
  status)
    status
    ;;
  logs)
    touch "$OUT_LOG"
    tail -f "$OUT_LOG"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 2
    ;;
esac
