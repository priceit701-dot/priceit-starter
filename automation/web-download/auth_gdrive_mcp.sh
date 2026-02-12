#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS_DIR="$BASE_DIR/secrets"
OAUTH_PATH="$SECRETS_DIR/gcp-oauth.keys.json"
CREDS_PATH="$SECRETS_DIR/gdrive-credentials.json"
mkdir -p "$SECRETS_DIR"

if [[ ! -f "$OAUTH_PATH" ]]; then
  echo "[ERROR] OAuth key file not found: $OAUTH_PATH"
  echo "Place your Google OAuth Desktop client JSON there first."
  exit 1
fi

export GDRIVE_OAUTH_PATH="$OAUTH_PATH"
export GDRIVE_CREDENTIALS_PATH="$CREDS_PATH"

npx -y @modelcontextprotocol/server-gdrive auth

echo "[OK] Auth completed. Credentials saved at: $CREDS_PATH"
