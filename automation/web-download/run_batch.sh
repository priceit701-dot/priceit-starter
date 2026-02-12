#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS_DIR="$BASE_DIR/secrets"
export GDRIVE_OAUTH_PATH="$SECRETS_DIR/gcp-oauth.keys.json"
export GDRIVE_CREDENTIALS_PATH="$SECRETS_DIR/gdrive-credentials.json"

echo "[$(date '+%F %T')] web-download batch start"
PY="$(cd "$BASE_DIR/../.." && pwd)/.venv/bin/python"
CFG="$BASE_DIR/sites.json"
if [ ! -f "$CFG" ]; then
  echo "sites.json not found. copy from sites.sample.json and fill urls"
  cp -n "$BASE_DIR/sites.sample.json" "$CFG" || true
fi

"$PY" - <<'PY'
import json, subprocess, pathlib
base = pathlib.Path('/Users/sanghun/.openclaw/workspace/priceit-starter/automation/web-download')
cfg = base / 'sites.json'
script = base / 'adminplus_auto_download.py'
ingest = base / 'ingest_downloads_to_db.py'
enqueue = base.parent.parent / 'scripts' / 'enqueue_priority_outbox.py'
push = base.parent.parent / 'scripts' / 'push_priority_outbox.py'
if not cfg.exists():
    print('skip: no sites.json')
    raise SystemExit(0)
rows = json.loads(cfg.read_text(encoding='utf-8'))
for r in rows:
    if not r.get('enabled'):
        continue
    if not r.get('url'):
        print(f"skip(no url): {r.get('site')}")
        continue
    cmd = [
        '/Users/sanghun/.openclaw/workspace/priceit-starter/.venv/bin/python',
        str(script), '--headless',
        '--site', r.get('site',''), '--id', r.get('id',''), '--pw', r.get('pw',''), '--url', r.get('url','')
    ]
    print('run:', r.get('site'))
    subprocess.run(cmd, check=False)

print('run: ingest_downloads_to_db')
subprocess.run(['/Users/sanghun/.openclaw/workspace/priceit-starter/.venv/bin/python', str(ingest)], check=False)

print('run: enqueue_priority_outbox')
subprocess.run(['/Users/sanghun/.openclaw/workspace/priceit-starter/.venv/bin/python', str(enqueue)], check=False)

print('run: push_priority_outbox')
subprocess.run(['/Users/sanghun/.openclaw/workspace/priceit-starter/.venv/bin/python', str(push)], check=False)
PY

echo "[$(date '+%F %T')] web-download batch end"
