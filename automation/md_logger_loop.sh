#!/bin/zsh
set -euo pipefail
cd /Users/sanghun/.openclaw/workspace/priceit-starter
while true; do
  ./.venv/bin/python automation/md_logger.py || true
  sleep 300
done
