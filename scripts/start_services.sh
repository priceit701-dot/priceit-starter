#!/bin/zsh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p logs

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" >> logs/watchdog.log; }

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_if_not_running() {
  local module="$1"
  local pidfile="$2"
  local logfile="$3"

  local -a pids
  pids=($(pgrep -f -- "-m $module" 2>/dev/null || true))
  if (( ${#pids[@]} > 0 )); then
    echo "${pids[1]}" > "$pidfile"
    if (( ${#pids[@]} > 1 )); then
      for pid in "${pids[@]:1}"; do
        if [[ "$pid" != "${pids[1]}" ]]; then
          kill "$pid" 2>/dev/null || true
          log "$module duplicate pid=$pid killed (keep=${pids[1]})"
        fi
      done
    fi
    echo "$module already running pid=${pids[1]}"
    return 0
  fi

  nohup "$PYTHON_BIN" -m "$module" >> "$logfile" 2>&1 &
  echo $! > "$pidfile"
  echo "$module started pid=$!"
}

start_if_not_running "src.api" "logs/api.pid" "logs/api.log"
start_if_not_running "src.kakao_clipboard_collector" "logs/collector.pid" "logs/collector.log"

WATCHDOG_PID=""
if [[ -f logs/watchdog.pid ]]; then
  WATCHDOG_PID="$(cat logs/watchdog.pid 2>/dev/null || true)"
fi

if is_pid_running "$WATCHDOG_PID"; then
  echo "watchdog already running pid=$WATCHDOG_PID"
else
  nohup "$ROOT_DIR/scripts/watchdog.sh" >> logs/watchdog.out 2>&1 &
  echo $! > logs/watchdog.pid
  echo "watchdog started pid=$!"
fi
