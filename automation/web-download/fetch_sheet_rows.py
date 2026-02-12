#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
import requests

SHEET_ID = os.getenv("SHEET_ID", "1b-RKWmC0s-ZdEPxCCzWGXfcWAnJ2cznPA8EteZx07YY")
SHEET_RANGE = os.getenv("SHEET_RANGE", "시트1!A1:Z200")
SECRETS_DIR = Path(__file__).resolve().parent / "secrets"
CRED_PATH = Path(os.getenv("GDRIVE_CREDENTIALS_PATH", SECRETS_DIR / "gdrive-credentials.json"))
OAUTH_PATH = Path(os.getenv("GDRIVE_OAUTH_PATH", SECRETS_DIR / "gcp-oauth.keys.json"))
OUT_PATH = Path(__file__).resolve().parent / "secrets" / "sheet_rows.json"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def refresh_access_token():
    cred = load_json(CRED_PATH)
    oauth = load_json(OAUTH_PATH)

    refresh_token = cred.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("refresh_token not found in gdrive-credentials.json")

    client_id = oauth.get("installed", {}).get("client_id") or oauth.get("client_id")
    client_secret = oauth.get("installed", {}).get("client_secret") or oauth.get("client_secret")
    token_uri = oauth.get("installed", {}).get("token_uri") or oauth.get("token_uri") or "https://oauth2.googleapis.com/token"

    if not client_id or not client_secret:
        raise RuntimeError("client_id/client_secret missing in gcp-oauth.keys.json")

    resp = requests.post(
        token_uri,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    resp.raise_for_status()
    tok = resp.json()
    if "access_token" not in tok:
        raise RuntimeError(f"No access_token in token response: {tok}")
    return tok["access_token"]


def fetch_rows(access_token: str):
    # 1) Try Google Sheets API values endpoint
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_RANGE}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    if resp.ok:
        return {"source": "sheets.values", **resp.json()}

    # 2) Fallback: Drive export (works with drive.readonly scope)
    export_url = f"https://www.googleapis.com/drive/v3/files/{SHEET_ID}/export"
    export_resp = requests.get(
        export_url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"mimeType": "text/csv"},
        timeout=30,
    )
    export_resp.raise_for_status()
    csv_text = export_resp.text
    rows = [line.split(",") for line in csv_text.splitlines() if line.strip()]
    return {
        "source": "drive.export.csv",
        "range": "csv-export",
        "values": rows,
    }


def main():
    access_token = refresh_access_token()
    data = fetch_rows(access_token)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    values = data.get("values", [])
    headers = values[0] if values else []
    print(f"Fetched rows: {max(len(values)-1, 0)}")
    print("Headers:", " | ".join(headers))
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
