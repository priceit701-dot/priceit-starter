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
import json
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
EVIDENCE_LOG = Path("./logs/kakao_collector_evidence.jsonl")

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

ROOM_RETRY_BUDGET = 2
CYCLE_FAILURE_BUDGET = 12
FOCUS_FAILURE_BUDGET = 4


class CollectorError(RuntimeError):
    code = "COLLECTOR_ERROR"


class FocusError(CollectorError):
    code = "FOCUS_LOST"


class SafetyStopError(CollectorError):
    code = "SAFETY_STOP"


def _log_evidence(level: str, code: str, room: str = "", step: str = "", detail: str = "", extra: dict | None = None):
    EVIDENCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "code": code,
        "room": room,
        "step": step,
        "detail": detail,
    }
    if extra:
        payload.update(extra)
    with EVIDENCE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        class _R:
            stdout = ""
            stderr = "timeout"
        return _R()


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
        _log_evidence("info", "CALIBRATED", step="calibrate", extra={"x": CURRENT_ROOM_LIST_X, "y0": CURRENT_ROOM_LIST_Y_START, "step_size": CURRENT_ROOM_LIST_Y_STEP, "score": best_score})


def _looks_like_noise_dump(text: str) -> bool:
    s = text.strip()
    if len(s) < 8:
        return True
    low = s.lower()
    token_hits = sum(1 for t in _UI_NOISE_TOKENS if t in low)
    return token_hits >= 3


def _text_sig(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _idle_seconds() -> float:
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
    cycle_failures = 0

    try:
        for i in range(rooms_per_cycle):
            scanned += 1
            room_name = f"{base_room_name}_{i+1:02d}"

            ok = False
            for attempt in range(1, ROOM_RETRY_BUDGET + 1):
                try:
                    _assert_kakao_focus()
                    _select_room_by_index(i)
                    _key(36)
                    time.sleep(max(ROOM_SWITCH_DELAY_SEC, 0.9))
                    text = _copy_chat_text()
                    if not text.strip():
                        raise CollectorError("empty clipboard dump")

                    if _looks_like_noise_dump(text):
                        skipped_noise += 1
                        _log_evidence("warn", "NOISE_DUMP", room=room_name, step="copy", detail=f"attempt={attempt}")
                        raise CollectorError("noise dump")

                    sig = _text_sig(text)
                    if prev_sig == sig:
                        same_sig_streak += 1
                    else:
                        same_sig_streak = 0
                    prev_sig = sig

                    if same_sig_streak >= 8:
                        _log_evidence("error", "ROOM_SWITCH_STUCK", room=room_name, step="room-switch", detail=f"streak={same_sig_streak}")
                        total_added += _ingest_text(f"{base_room_name}_LIVE", text)
                        print("collector fallback | switching stuck -> live room ingest", flush=True)
                        return total_added

                    if last_sig_by_room.get(room_name) == sig:
                        skipped_same += 1

                    last_sig_by_room[room_name] = sig
                    added = _ingest_text(room_name, text)
                    total_added += added
                    _log_evidence("info", "ROOM_OK", room=room_name, step="ingest", extra={"attempt": attempt, "added": added, "sig": sig[:12]})
                    ok = True
                    break
                except FocusError as e:
                    _log_evidence("error", "FOCUS_LOST", room=room_name, step="focus-check", detail=str(e), extra={"attempt": attempt})
                    raise
                except CollectorError as e:
                    cycle_failures += 1
                    _log_evidence("warn", "ROOM_RETRY", room=room_name, step="collect", detail=str(e), extra={"attempt": attempt, "retry_budget": ROOM_RETRY_BUDGET})
                    time.sleep(0.5 * attempt)

            if not ok:
                cycle_failures += 1
                _log_evidence("error", "ROOM_GIVEUP", room=room_name, step="collect", detail=f"retry_exhausted budget={ROOM_RETRY_BUDGET}")

            if cycle_failures >= CYCLE_FAILURE_BUDGET:
                raise SafetyStopError(f"cycle failure budget exceeded: {cycle_failures}/{CYCLE_FAILURE_BUDGET}")
    finally:
        pass

    print(
        f"cycle stats | scanned={scanned} added={total_added} skipped_same={skipped_same} skipped_noise={skipped_noise} failures={cycle_failures}",
        flush=True,
    )
    _log_evidence("info", "CYCLE_DONE", step="cycle", extra={"scanned": scanned, "added": total_added, "skipped_same": skipped_same, "skipped_noise": skipped_noise, "failures": cycle_failures})
    return total_added


def main():
    init_db()
    print(
        f"collector started | base_room={KAKAO_ROOM_NAME} | rooms_per_cycle={ROOMS_PER_CYCLE} | interval={COLLECT_INTERVAL_SEC}s",
        flush=True,
    )

    last_sig_by_room = {}
    focus_failures = 0
    while True:
        try:
            idle_s = _idle_seconds()
            if COLLECT_ONLY_WHEN_IDLE_SEC > 0 and idle_s < COLLECT_ONLY_WHEN_IDLE_SEC:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] skip cycle (user active, idle={idle_s:.1f}s)",
                    flush=True,
                )
                _log_evidence("info", "SKIP_ACTIVE_USER", step="idle-check", detail=f"idle={idle_s:.2f}s")
            else:
                added = collect_cycle(KAKAO_ROOM_NAME, ROOMS_PER_CYCLE, last_sig_by_room)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] cycle done +{added}", flush=True)
                focus_failures = 0
        except FocusError as e:
            focus_failures += 1
            print(f"collector focus warning: {e}", flush=True)
            _log_evidence("error", "FOCUS_LOST", step="cycle", detail=str(e), extra={"focus_failures": focus_failures})
            try:
                _activate_kakao()
            except Exception:
                pass
            if focus_failures >= FOCUS_FAILURE_BUDGET:
                _log_evidence("critical", "SAFETY_STOP", step="cycle", detail=f"focus failure budget exceeded: {focus_failures}/{FOCUS_FAILURE_BUDGET}")
                print("collector safety stop: focus failure budget exceeded", flush=True)
                break
        except SafetyStopError as e:
            _log_evidence("critical", "SAFETY_STOP", step="cycle", detail=str(e))
            print(f"collector safety stop: {e}", flush=True)
            break
        except KeyboardInterrupt:
            print("stopped", flush=True)
            _log_evidence("info", "STOPPED", step="signal", detail="keyboard_interrupt")
            break
        except Exception as e:
            print("collector error:", e, flush=True)
            _log_evidence("error", "UNHANDLED", step="cycle", detail=str(e))
        time.sleep(COLLECT_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        with _single_instance_lock(LOCK_FILE):
            main()
    except RuntimeError as e:
        print(str(e), flush=True)
        _log_evidence("warn", "LOCKED", step="startup", detail=str(e))
