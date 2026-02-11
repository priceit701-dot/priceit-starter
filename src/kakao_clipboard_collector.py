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
import re
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
    COLLECT_ONLY_WHEN_IDLE_SEC,
    ROOM_LIST_X,
    ROOM_LIST_Y_START,
    ROOM_LIST_Y_STEP,
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

CURRENT_ROOM_LIST_X = ROOM_LIST_X
CURRENT_ROOM_LIST_Y_START = ROOM_LIST_Y_START
CURRENT_ROOM_LIST_Y_STEP = ROOM_LIST_Y_STEP


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


def _activate_app(app_name: str):
    _run_applescript(f'tell application "{app_name}" to activate')
    time.sleep(0.25)


def _activate_kakao():
    _activate_app("KakaoTalk")
    time.sleep(0.25)


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


def _click(x: int, y: int):
    _run_applescript(f'tell application "System Events" to click at {{{x}, {y}}}')


def _select_room_by_index(i: int):
    y = CURRENT_ROOM_LIST_Y_START + (i * CURRENT_ROOM_LIST_Y_STEP)
    _click(CURRENT_ROOM_LIST_X, y)
    time.sleep(0.10)


def _auto_calibrate_room_list():
    global CURRENT_ROOM_LIST_X, CURRENT_ROOM_LIST_Y_START, CURRENT_ROOM_LIST_Y_STEP
    x_candidates = [ROOM_LIST_X - 40, ROOM_LIST_X, ROOM_LIST_X + 40, 180, 220, 260]
    y_candidates = [ROOM_LIST_Y_START - 80, ROOM_LIST_Y_START, ROOM_LIST_Y_START + 80, 280, 340]
    step_candidates = [ROOM_LIST_Y_STEP - 12, ROOM_LIST_Y_STEP, ROOM_LIST_Y_STEP + 12, 72, 86]

    best = None
    best_score = -1
    for x in x_candidates:
        if x < 80:
            continue
        for y0 in y_candidates:
            if y0 < 160:
                continue
            for step in step_candidates:
                if step < 48:
                    continue
                sigs = set()
                noise = 0
                for i in range(3):
                    _click(int(x), int(y0 + i * step))
                    time.sleep(0.10)
                    txt = _copy_chat_text()
                    if _looks_like_noise_dump(txt):
                        noise += 1
                        continue
                    sigs.add(_text_sig(txt))
                score = (len(sigs) * 10) - (noise * 5)
                if score > best_score:
                    best_score = score
                    best = (int(x), int(y0), int(step))

    if best:
        CURRENT_ROOM_LIST_X, CURRENT_ROOM_LIST_Y_START, CURRENT_ROOM_LIST_Y_STEP = best
        print(
            f"collector calibrate | x={CURRENT_ROOM_LIST_X} y0={CURRENT_ROOM_LIST_Y_START} step={CURRENT_ROOM_LIST_Y_STEP} score={best_score}",
            flush=True,
        )


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


def _idle_seconds() -> float:
    """macOS HID idle seconds (best-effort)."""
    p = subprocess.run(
        ["ioreg", "-c", "IOHIDSystem"],
        capture_output=True,
        text=True,
        check=False,
    )
    out = p.stdout or ""
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    if not m:
        return 0.0
    # ns -> s
    return int(m.group(1)) / 1_000_000_000.0


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
    _auto_calibrate_room_list()

    total_added = 0
    scanned = 0
    skipped_noise = 0
    skipped_same = 0
    same_sig_streak = 0
    prev_sig = None

    try:
        for i in range(rooms_per_cycle):
            scanned += 1
            room_name = f"{base_room_name}_{i+1:02d}"

            _assert_kakao_focus()
            _select_room_by_index(i)
            time.sleep(ROOM_SWITCH_DELAY_SEC)
            text = _copy_chat_text()

            if _looks_like_noise_dump(text):
                skipped_noise += 1
                continue

            sig = _text_sig(text)
            if prev_sig == sig:
                same_sig_streak += 1
            else:
                same_sig_streak = 0
            prev_sig = sig

            # room switch가 실제로 안 되고 같은 화면만 반복될 때 조기 감지
            if same_sig_streak >= 8:
                raise FocusError("room switching appears stuck (same screen repeatedly)")

            if last_sig_by_room.get(room_name) == sig:
                skipped_same += 1

            # 핵심: 시그니처 동일여부와 무관하게 항상 ingest 시도(중복은 DB hash가 차단)
            last_sig_by_room[room_name] = sig
            total_added += _ingest_text(room_name, text)
    finally:
        pass

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
            idle_s = _idle_seconds()
            if COLLECT_ONLY_WHEN_IDLE_SEC > 0 and idle_s < COLLECT_ONLY_WHEN_IDLE_SEC:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] skip cycle (user active, idle={idle_s:.1f}s)",
                    flush=True,
                )
            else:
                added = collect_cycle(KAKAO_ROOM_NAME, ROOMS_PER_CYCLE, last_sig_by_room)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] cycle done +{added}", flush=True)
        except FocusError as e:
            print(f"collector focus warning: {e}", flush=True)
            # 다음 사이클 전에 포커스 복구 시도
            try:
                _activate_kakao()
            except Exception:
                pass
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
