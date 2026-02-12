#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS_DIR="$BASE_DIR/secrets"
export GDRIVE_OAUTH_PATH="$SECRETS_DIR/gcp-oauth.keys.json"
export GDRIVE_CREDENTIALS_PATH="$SECRETS_DIR/gdrive-credentials.json"

echo "[$(date '+%F %T')] web-download batch start"
# TODO: MCP 호출부 연결 (search/list/download)
echo "[$(date '+%F %T')] web-download batch end"
