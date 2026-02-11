import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import httpx

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

STATE_PATH = Path("./logs/telegram_notify_state.json")
DEFAULT_MAX_RETRY = 4
DEFAULT_BASE_BACKOFF_SEC = 1.2
DEFAULT_MAX_BACKOFF_SEC = 15.0
DEFAULT_SENT_CACHE_LIMIT = 4000


def _ensure_state_file():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps({"sent": {}, "history": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_state() -> dict:
    _ensure_state_file()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"sent": {}, "history": []}
        data.setdefault("sent", {})
        data.setdefault("history", [])
        return data
    except Exception:
        return {"sent": {}, "history": []}


def _save_state(state: dict):
    _ensure_state_file()
    # 최근 전송 idempotency key만 유지 (파일 비대화 방지)
    sent = state.get("sent", {})
    if len(sent) > DEFAULT_SENT_CACHE_LIMIT:
        items = sorted(sent.items(), key=lambda kv: kv[1].get("sent_at", ""), reverse=True)
        sent = dict(items[:DEFAULT_SENT_CACHE_LIMIT])
        state["sent"] = sent
    history = state.get("history", [])
    state["history"] = history[-200:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_idempotency_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def send_telegram(text: str, idempotency_key: Optional[str] = None) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    key = idempotency_key or _default_idempotency_key(text)
    state = _load_state()
    sent = state.get("sent", {})

    if key in sent:
        state["history"].append({"event": "dedup_skip", "key": key, "text_head": text[:80], "ts": time.time()})
        _save_state(state)
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    last_error = None
    with httpx.Client(timeout=10.0) as client:
        for attempt in range(1, DEFAULT_MAX_RETRY + 1):
            try:
                r = client.post(url, json=payload)
                if 200 <= r.status_code < 300:
                    sent[key] = {"sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "status_code": r.status_code}
                    state["sent"] = sent
                    state["history"].append({"event": "sent", "key": key, "attempt": attempt, "status_code": r.status_code, "ts": time.time()})
                    _save_state(state)
                    return True
                last_error = f"http_{r.status_code}"
            except Exception as e:
                last_error = str(e)

            if attempt < DEFAULT_MAX_RETRY:
                wait_sec = min(DEFAULT_BASE_BACKOFF_SEC * (2 ** (attempt - 1)), DEFAULT_MAX_BACKOFF_SEC)
                time.sleep(wait_sec)

    state["history"].append({"event": "failed", "key": key, "error": last_error, "ts": time.time()})
    _save_state(state)
    return False
