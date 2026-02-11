#!/bin/zsh
set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "[1] syntax check"
"$PYTHON_BIN" -m py_compile src/kakao_clipboard_collector.py src/api.py

printf "\n[2] duplicate process check\n"
pgrep -af "src.api|src.kakao_clipboard_collector|scripts/watchdog.sh" || true

printf "\n[3] pidfile health\n"
for f in logs/api.pid logs/collector.pid logs/watchdog.pid; do
  [[ -f "$f" ]] && echo "$f => $(cat "$f")" || echo "$f => (missing)"
done

printf "\n[4] recent logs\n"
tail -n 20 logs/watchdog.log 2>/dev/null || true
tail -n 20 logs/collector.log 2>/dev/null || true

echo "\nDONE"
