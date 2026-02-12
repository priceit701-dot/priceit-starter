#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from Quartz import (
    CGEventCreateMouseEvent,
    CGEventPost,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGHIDEventTap,
)

ROOT = Path("/Users/sanghun/.openclaw/workspace/priceit-starter")
SKILL = "/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py"
LOCK = ROOT / "logs" / "kakao_alert_sm.lock"
LOG = ROOT / "logs" / "kakao_alert_only_export_loop.log"
COORD_MD = ROOT / "docs" / "kakao-coordinate-lock.md"


@dataclass
class Coords:
    rooms: list[tuple[int, int]]
    hamburger: tuple[int, int]
    manage: tuple[int, int]
    textsave: tuple[int, int]
    save: tuple[int, int]
    done: tuple[int, int]


def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def run(cmd: list[str], quiet=False) -> str:
    stderr = subprocess.DEVNULL if quiet else None
    return subprocess.check_output(cmd, stderr=stderr).decode("utf-8", "ignore")


def abs_click(x: int, y: int):
    for et in (kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp):
        ev = CGEventCreateMouseEvent(None, et, (float(x), float(y)), 0)
        CGEventPost(kCGHIDEventTap, ev)
        time.sleep(0.02)


def safe_click(x: int, y: int):
    activate_kakao()
    time.sleep(0.06)
    abs_click(x, y)


def activate_kakao():
    subprocess.run(["osascript", "-e", 'tell application "KakaoTalk" to activate'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def key(combo: str):
    subprocess.run(["python3", SKILL, "key", "--app", "카카오톡", combo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def windows() -> list[dict]:
    try:
        return json.loads(run(["python3", SKILL, "list"], quiet=True))
    except Exception:
        return []


def resolve_main_window() -> dict | None:
    arr = windows()
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "카카오톡":
            return w
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "로그인":
            return w
    return None


def resolve_settings_window(main_id: int | str) -> dict | None:
    arr = windows()
    # 1) 제목 힌트 우선
    for w in arr:
        if w.get("app") == "카카오톡" and str(w.get("id")) != str(main_id):
            t = str(w.get("title") or "")
            if t in ("Window", "채팅방 설정") or "설정" in t or "대화" in t:
                return w
    # 2) 제목이 비어 있어도 메인 제외 카카오 보조창이면 허용
    for w in arr:
        if w.get("app") == "카카오톡" and str(w.get("id")) != str(main_id):
            return w
    return None


def latest_export_after(start_ts: int) -> str | None:
    candidates = []
    for p in Path.home().glob("Downloads/KakaoTalk_Chat_*.csv"):
        try:
            mt = int(p.stat().st_mtime)
        except Exception:
            continue
        if mt >= start_ts:
            candidates.append((mt, str(p), p.stat().st_size))
    candidates.sort(reverse=True)
    if not candidates:
        return None
    mt, path, size = candidates[0]
    return f"{mt}\t{size}\t{path}"


def parse_coord_md() -> Coords:
    txt = COORD_MD.read_text(encoding="utf-8")
    rooms = []
    for i in range(1, 9):
        m = re.search(rf"room{i}:\s*`?\((\d+),(\d+)\)`?", txt)
        if not m:
            raise RuntimeError(f"room{i} not found in {COORD_MD}")
        rooms.append((int(m.group(1)), int(m.group(2))))

    def one(label: str) -> tuple[int, int]:
        m = re.search(rf"{re.escape(label)}:\s*`?\((\d+),(\d+)\)`?", txt)
        if not m:
            raise RuntimeError(f"{label} not found in {COORD_MD}")
        return int(m.group(1)), int(m.group(2))

    return Coords(
        rooms=rooms,
        hamburger=one("햄버거/설정"),
        manage=one("대화내용관리"),
        textsave=one("텍스트 파일로 저장"),
        save=one("저장"),
        done=one("완료"),
    )


def _detect_once() -> list[int]:
    try:
        out = run(["python3", str(ROOT / "scripts" / "detect_badge_rows.py")], quiet=True).strip()
        rows = json.loads(out) if out else []
        return [int(x) for x in rows]
    except Exception:
        return []


def detect_alert_rows() -> list[int]:
    # 2회 감지 교집합으로 오탐을 줄이면서 red-only 미탐 보완
    a = set(_detect_once())
    time.sleep(0.45)
    b = set(_detect_once())
    inter = sorted(a & b)
    return inter






def room_title_non_main(main_id: int | str) -> str:
    arr = windows()
    banned = {"", "Window", "저장", "완료", "확인", "취소", "카카오톡", "로그인"}
    for w in arr:
        if w.get("app") == "카카오톡" and str(w.get("id")) != str(main_id):
            t = str(w.get("title") or "").strip()
            if t in banned:
                continue
            if len(t) <= 2:
                continue
            return t
    return ""
def nearest_room_by_y(rows: list[tuple[int, int]], y: int) -> tuple[int, int] | None:
    if not rows:
        return None
    n = min(rows, key=lambda xy: abs(xy[1] - y))
    return n if abs(n[1] - y) <= 40 else None
def close_chat_window(main_id: int | str):
    # 저장 완료 후 대화창만 닫기 (메인창 제외)
    arr = windows()
    target = None
    for w in arr:
        if w.get("app") == "카카오톡" and str(w.get("id")) != str(main_id):
            t = str(w.get("title") or "")
            if t and t != "Window":
                target = w
                break
    if not target:
        return
    x = int(target.get("x", 400) + min(120, target.get("w", 380) // 3))
    y = int(target.get("y", 30) + 20)
    safe_click(x, y)
    time.sleep(0.05)
    key("cmd+w")


def run_once() -> None:
    activate_kakao()
    main = resolve_main_window()
    if not main:
        log("WARN main_window_not_found")
        return
    main_id = main.get("id")

    coords = parse_coord_md()
    detected = detect_alert_rows()
    log(f"alert_rows={detected}")
    if not detected:
        return

    # 운영 모드: 감지된 알람 행 전체 처리
    for ry in detected:
        room_xy = nearest_room_by_y(coords.rooms, ry)
        if not room_xy:
            continue
        x, y = room_xy
        # room open (사용자 힌트: 선택 후 엔터)
        safe_click(x, y)
        time.sleep(0.22)
        key("return")
        time.sleep(0.75)

        room = room_title_non_main(main_id)
        log(f"ROOM_OPENED y={ry} room={room}")

        # 결정론 모드: 방 제목이 비어있으면 즉시 스킵
        if not room:
            log(f"SKIP_EMPTY_ROOM y={ry}")
            close_chat_window(main_id)
            continue

        start = int(time.time())

        # settings -> save flow
        safe_click(*coords.hamburger)
        time.sleep(0.25)
        key("opt+cmd+,")

        sw = None
        for _ in range(8):
            time.sleep(0.25)
            sw = resolve_settings_window(main_id)
            if sw:
                break

        if not sw:
            log(f"WARN settings_window_not_found room={room}")
            continue
        log(f"SETTINGS_OPENED y={ry} room={room} wid={sw.get('id')}")

        safe_click(*coords.manage)
        log(f"MANAGE_CLICKED y={ry} room={room}")
        time.sleep(0.4)
        safe_click(*coords.textsave)
        log(f"TEXT_SAVE_CLICKED y={ry} room={room}")
        time.sleep(0.55)
        safe_click(*coords.save)
        log(f"SAVE_CLICKED y={ry} room={room}")
        # 사용자 힌트: 저장 후 엔터 2회 -> 완료 버튼 노출
        time.sleep(0.35)
        key("return")
        log(f"ENTER1 y={ry} room={room}")
        time.sleep(0.35)
        key("return")
        log(f"ENTER2 y={ry} room={room}")
        time.sleep(0.45)
        safe_click(*coords.done)
        log(f"DONE_CLICKED y={ry} room={room}")
        time.sleep(0.9)

        newf = None
        for _ in range(8):
            newf = latest_export_after(start)
            if newf:
                break
            time.sleep(0.35)
        if newf:
            log(f"OK y={ry} room={room} file={newf}")
            close_chat_window(main_id)
        else:
            log(f"MISS y={ry} room={room} file=NONE")


def main_loop(once=False):
    interval = int(os.getenv("KAKAO_ALERT_INTERVAL_SECONDS", "60"))
    if LOCK.exists():
        log("already running (lock exists)")
        return
    LOCK.write_text(str(time.time()), encoding="utf-8")
    try:
        log(f"start alert-only export loop interval={interval}s")
        while True:
            run_once()
            if once:
                break
            time.sleep(interval)
        log("finish alert-only export loop")
    finally:
        try:
            LOCK.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    once = len(sys.argv) >= 2 and sys.argv[1] == "--once"
    main_loop(once=once)
