"""
A안(안정형) 수집기 (macOS):
- 현재 활성 창(카카오톡 대화창)에서 Command+A, Command+C를 AppleScript로 실행
- 클립보드(pbpaste)에서 신규 라인만 추출해 DB에 적재
"""

import subprocess
import time
from datetime import datetime

from .config import KAKAO_ROOM_NAME, COLLECT_INTERVAL_SEC
from .db import init_db
from .pipeline import ingest_line


def _run_applescript(script: str):
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _copy_all_from_active_window():
    # CMD+A
    _run_applescript('tell application "System Events" to keystroke "a" using {command down}')
    time.sleep(0.12)
    # CMD+C
    _run_applescript('tell application "System Events" to keystroke "c" using {command down}')
    time.sleep(0.20)


def _pbpaste() -> str:
    p = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    return p.stdout or ""


def collect_once(room_name: str):
    before = _pbpaste()
    _copy_all_from_active_window()
    text = _pbpaste()
    if not text or text == before:
        return 0

    count = 0
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 2:
            continue
        if ingest_line(room_name, line, sender="kakao", created_at=datetime.now().isoformat(timespec="seconds")):
            count += 1
    return count


def main():
    init_db()
    print(f"collector started | room={KAKAO_ROOM_NAME} | interval={COLLECT_INTERVAL_SEC}s")
    while True:
        try:
            added = collect_once(KAKAO_ROOM_NAME)
            if added:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] +{added}")
        except KeyboardInterrupt:
            print("stopped")
            break
        except Exception as e:
            print("collector error:", e)
        time.sleep(COLLECT_INTERVAL_SEC)


if __name__ == "__main__":
    main()
