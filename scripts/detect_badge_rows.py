#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

from PIL import Image

# screen-space anchor rows (from coordinate lock)
ROW_Y_SCREEN = [126, 205, 269, 344, 417, 490, 563, 636]
SKILL = "/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py"


def _windows():
    try:
        out = subprocess.check_output(["python3", SKILL, "list"], stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
        return json.loads(out)
    except Exception:
        return []


def _main_window():
    arr = _windows()
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "카카오톡":
            return w
    for w in arr:
        if w.get("app") == "카카오톡":
            return w
    return None


def _screen_y_to_canvas_y(y_screen: int, win_y: int, win_h: int) -> int:
    # mac_use screenshot canvas is 1000x1000 (aspect-fit), Kakao list window is tall so y uses full height
    rel = (y_screen - win_y) / max(1, win_h)
    return int(max(0, min(999, rel * 1000)))


def is_red(r: int, g: int, b: int) -> bool:
    return r > 165 and g < 130 and b < 130 and (r - g) > 35 and (r - b) > 35


def main():
    mw = _main_window()
    if not mw:
        print("[]")
        return

    wid = str(mw.get("id"))
    win_y = int(mw.get("y", 0))
    win_h = int(mw.get("h", 1))

    try:
        out = subprocess.check_output(["python3", SKILL, "screenshot", "카카오톡", "--id", wid], stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
        obj = json.loads(out)
    except Exception:
        print("[]")
        return

    img_path = obj.get("file")
    if not img_path or not Path(img_path).exists():
        print("[]")
        return

    im = Image.open(img_path).convert("RGB")
    w, h = im.size

    # badge zone on 1000 canvas: right side of list panel
    x1, x2 = int(w * 0.74), int(w * 0.93)

    # convert screen anchors -> canvas anchors
    row_canvas = [(_screen_y_to_canvas_y(y, win_y, win_h), y) for y in ROW_Y_SCREEN]

    rows = []
    for cy, sy in row_canvas:
        y1, y2 = max(0, cy - 22), min(h - 1, cy + 22)
        red = 0
        for py in range(y1, y2 + 1, 2):
            for px in range(x1, x2 + 1, 2):
                r, g, b = im.getpixel((px, py))
                if is_red(r, g, b):
                    red += 1
        if red >= 18:
            rows.append(sy)

    print(json.dumps(rows))


if __name__ == "__main__":
    main()
