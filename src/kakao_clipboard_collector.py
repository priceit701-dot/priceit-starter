"""
A안 자동 수집기 (macOS, KakaoTalk 데스크톱)
- 카카오톡 활성화
- 채팅 목록을 아래로 순회하며 각 방 텍스트 복사
- 신규 라인만 DB 적재

주의:
- macOS 손쉬운 사용(Accessibility)에서 Terminal/Python 허용 필요
- 카카오톡 창에서 채팅 목록 포커스가 가능한 상태여야 함
"""

import subprocess
import time
from datetime import datetime

from .config import (
    KAKAO_ROOM_NAME,
    COLLECT_INTERVAL_SEC,
    ROOMS_PER_CYCLE,
    ROOM_SWITCH_DELAY_SEC,
)
from .db import init_db
from .pipeline import ingest_line


def _run_applescript(script: str):
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _activate_kakao():
    _run_applescript('tell application "KakaoTalk" to activate')
    time.sleep(0.4)


def _key(keycode: int):
    _run_applescript(f'tell application "System Events" to key code {keycode}')


def _cmd_key(char: str):
    _run_applescript(
        f'tell application "System Events" to keystroke "{char}" using {{command down}}'
    )


def _pbpaste() -> str:
    p = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    return p.stdout or ""


def _copy_chat_text() -> str:
    _cmd_key("a")
    time.sleep(0.10)
    _cmd_key("c")
    time.sleep(0.18)
    return _pbpaste()


def _move_next_room():
    # down arrow
    _key(125)
    time.sleep(0.08)
    # enter
    _key(36)


def _ingest_text(room_name: str, text: str) -> int:
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 2:
            continue
        if ingest_line(
            room_name,
            line,
            sender="kakao",
            created_at=datetime.now().isoformat(timespec="seconds"),
        ):
            count += 1
    return count


def collect_cycle(base_room_name: str, rooms_per_cycle: int) -> int:
    _activate_kakao()
    total_added = 0

    # 첫 방에서 시작
    _key(36)
    time.sleep(ROOM_SWITCH_DELAY_SEC)

    for i in range(rooms_per_cycle):
        text = _copy_chat_text()
        room_name = f"{base_room_name}_{i+1:02d}"
        if text:
            total_added += _ingest_text(room_name, text)
        _move_next_room()
        time.sleep(ROOM_SWITCH_DELAY_SEC)

    return total_added


def main():
    init_db()
    print(
        f"collector started | base_room={KAKAO_ROOM_NAME} | rooms_per_cycle={ROOMS_PER_CYCLE} | interval={COLLECT_INTERVAL_SEC}s"
    )
    while True:
        try:
            added = collect_cycle(KAKAO_ROOM_NAME, ROOMS_PER_CYCLE)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] cycle done +{added}")
        except KeyboardInterrupt:
            print("stopped")
            break
        except Exception as e:
            print("collector error:", e)
        time.sleep(COLLECT_INTERVAL_SEC)


if __name__ == "__main__":
    main()
