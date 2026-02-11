"""
A안 자동 수집기 (macOS, KakaoTalk 데스크톱)
- 카카오톡 활성화/포커스 확인
- 채팅 목록을 아래로 순회하며 각 방 텍스트 복사
- 신규 라인만 DB 적재

안정화 포인트
- 단일 인스턴스 락으로 중복 실행 방지
- 포커스 검증 실패 시 키 입력 중단(오입력 방지)
- 클립보드 원복으로 사용자 작업 간섭 완화
- UI 노이즈/비정상 텍스트는 방 단위 스킵
"""

import fcntl
import hashlib
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import (
    KAKAO_ROOM_NAME,
    COLLECT_INTERVAL_SEC,
    ROOMS_PER_CYCLE,
    ROOM_SWITCH_DELAY_SEC,
)
from .db import init_db
from .pipeline import ingest_line

LOCK_FILE = Path("./logs/collector.lock")

_UI_NOISE_TOKENS = [
    "open chat",
    "kakaotalk",
    "search",
    "settings",
    "friends",
    "chats",
    "more",
    "border:",
    "padding:",
    "box-sizing",
    "counter-reset",
]


class FocusError(RuntimeError):
    pass


@contextmanager
def _single_instance_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise RuntimeError(f"collector already running: {path}")

    f.write(str(os.getpid()))
    f.flush()
    try:
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def _run_applescript(script: str):
    return subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)


def _frontmost_app_name() -> str:
    p = _run_applescript('tell application "System Events" to get name of first process whose frontmost is true')
    return (p.stdout or "").strip()


def _activate_kakao():
    _run_applescript('tell application "KakaoTalk" to activate')
    time.sleep(0.5)


def _assert_kakao_focus():
    app = _frontmost_app_name()
    if app != "KakaoTalk":
        raise FocusError(f"front app is '{app}', not KakaoTalk")


def _key(keycode: int):
    _run_applescript(f'tell application "System Events" to key code {keycode}')


def _cmd_key(char: str):
    _run_applescript(
        f'tell application "System Events" to keystroke "{char}" using {{command down}}'
    )


def _pbpaste() -> str:
    p = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    return p.stdout or ""


def _pbcopy(text: str):
    subprocess.run(["pbcopy"], input=text, text=True, capture_output=True, check=False)


def _copy_chat_text() -> str:
    original_clipboard = _pbpaste()
    try:
        _cmd_key("a")
        time.sleep(0.10)
        _cmd_key("c")
        time.sleep(0.20)
        return _pbpaste()
    finally:
        # 사용자 클립보드 오염 최소화
        _pbcopy(original_clipboard)


def _move_next_room():
    _key(125)  # down arrow
    time.sleep(0.08)
    _key(36)  # enter


def _looks_like_noise_dump(text: str) -> bool:
    s = text.strip()
    if len(s) < 8:
        return True
    low = s.lower()
    token_hits = sum(1 for t in _UI_NOISE_TOKENS if t in low)
    # UI 문자열 다량 포함 시 잘못된 포커스/복사로 간주
    return token_hits >= 3


def _text_sig(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


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


def collect_cycle(base_room_name: str, rooms_per_cycle: int, last_sig_by_room: dict) -> int:
    _activate_kakao()
    _assert_kakao_focus()

    total_added = 0
    scanned = 0
    skipped_noise = 0
    skipped_same = 0

    # 첫 방에서 시작
    _key(36)
    time.sleep(ROOM_SWITCH_DELAY_SEC)

    for i in range(rooms_per_cycle):
        scanned += 1
        room_name = f"{base_room_name}_{i+1:02d}"

        _assert_kakao_focus()
        text = _copy_chat_text()

        if _looks_like_noise_dump(text):
            skipped_noise += 1
            _move_next_room()
            time.sleep(ROOM_SWITCH_DELAY_SEC)
            continue

        sig = _text_sig(text)
        if last_sig_by_room.get(room_name) == sig:
            skipped_same += 1
        else:
            last_sig_by_room[room_name] = sig
            total_added += _ingest_text(room_name, text)

        _move_next_room()
        time.sleep(ROOM_SWITCH_DELAY_SEC)

    print(
        f"cycle stats | scanned={scanned} added={total_added} skipped_same={skipped_same} skipped_noise={skipped_noise}",
        flush=True,
    )
    return total_added


def main():
    init_db()
    print(
        f"collector started | base_room={KAKAO_ROOM_NAME} | rooms_per_cycle={ROOMS_PER_CYCLE} | interval={COLLECT_INTERVAL_SEC}s",
        flush=True,
    )

    last_sig_by_room = {}
    while True:
        try:
            added = collect_cycle(KAKAO_ROOM_NAME, ROOMS_PER_CYCLE, last_sig_by_room)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] cycle done +{added}", flush=True)
        except FocusError as e:
            print(f"collector focus warning: {e}", flush=True)
        except KeyboardInterrupt:
            print("stopped", flush=True)
            break
        except Exception as e:
            print("collector error:", e, flush=True)
        time.sleep(COLLECT_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        with _single_instance_lock(LOCK_FILE):
            main()
    except RuntimeError as e:
        print(str(e), flush=True)
