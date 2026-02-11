"""
A안(안정형) 수집기:
- 현재 활성화된 카카오톡 대화창에서 텍스트를 복사(Command+A, Command+C)
- 클립보드에서 신규 라인만 추출해서 DB 적재
"""

import time
from datetime import datetime
import pyautogui
import pyperclip
from .config import KAKAO_ROOM_NAME, COLLECT_INTERVAL_SEC
from .db import init_db
from .pipeline import ingest_line


def collect_once(room_name: str):
    before = pyperclip.paste()
    pyautogui.hotkey("command", "a")
    time.sleep(0.15)
    pyautogui.hotkey("command", "c")
    time.sleep(0.2)
    text = pyperclip.paste()
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
