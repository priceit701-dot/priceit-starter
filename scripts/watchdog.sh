#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
mkdir -p logs

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

WATCHDOG_LOCK_DIR="logs/watchdog.lock.d"
if ! mkdir "$WATCHDOG_LOCK_DIR" 2>/dev/null; then
  echo "watchdog already running (lock exists: $WATCHDOG_LOCK_DIR)"
  exit 0
fi
trap 'rmdir "$WATCHDOG_LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

echo $$ > logs/watchdog.pid

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" >> logs/watchdog.log; }

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

is_port_occupied() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

refresh_pidfile_from_process() {
  local module="$1"
  local pidfile="$2"
  local -a pids
  pids=($(pgrep -f -- "-m $module" 2>/dev/null || true))

  if (( ${#pids[@]} == 0 )); then
    return 1
  fi

  local keep_pid="${pids[1]}"
  if (( ${#pids[@]} > 1 )); then
    for pid in "${pids[@]:1}"; do
      if [[ "$pid" != "$keep_pid" ]]; then
        kill "$pid" 2>/dev/null || true
        log "$module duplicate pid=$pid killed (keep=$keep_pid)"
      fi
    done
  fi

  echo "$keep_pid" > "$pidfile"
  return 0
}

start_if_down() {
  local module="$1"
  local pidfile="$2"
  local logfile="$3"
  local cooldown_sec=60

  local pid=""
  if [[ -f "$pidfile" ]]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
  fi

  if is_pid_running "$pid"; then
    return 0
  fi

  if refresh_pidfile_from_process "$module" "$pidfile"; then
    return 0
  fi

  # api 포트가 이미 점유되면 타 프로세스가 떠있는 것으로 간주하고 재시작 루프 중단
  if [[ "$module" == "src.api" ]] && is_port_occupied 8877; then
    log "$module port 8877 already occupied -> skip restart"
    return 0
  fi

  local key="${module//./_}"
  local stamp="logs/${key}.restart.ts"
  local now="$(date +%s)"
  local last="0"
  if [[ -f "$stamp" ]]; then
    last="$(cat "$stamp" 2>/dev/null || echo 0)"
  fi
  if (( now - last < cooldown_sec )); then
    log "$module restart suppressed (cooldown ${cooldown_sec}s)"
    return 0
  fi

  log "$module down -> restart"
  nohup "$PYTHON_BIN" -m "$module" >> "$logfile" 2>&1 &
  echo $! > "$pidfile"
  echo "$now" > "$stamp"
}

log "watchdog started python=$PYTHON_BIN"
while true; do
  start_if_down "src.api" "logs/api.pid" "logs/api.log"
  start_if_down "src.kakao_clipboard_collector" "logs/collector.pid" "logs/collector.log"
  sleep 15
done
