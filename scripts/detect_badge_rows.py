#!/usr/bin/env python3
import json
import re
import subprocess
from pathlib import Path

from PIL import Image
import pytesseract

Y_ROWS = [126, 205, 269, 344, 417, 490, 563, 636]
SKILL = "/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py"


def nearest_row(y: int):
    n = min(Y_ROWS, key=lambda yy: abs(yy - y))
    return n if abs(n - y) <= 45 else None


def _resolve_main_window_id() -> str:
    try:
        out = subprocess.check_output(["python3", SKILL, "list"], stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
        arr = json.loads(out)
    except Exception:
        return ""
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "카카오톡":
            return str(w.get("id"))
    for w in arr:
        if w.get("app") == "카카오톡":
            return str(w.get("id"))
    return ""


def main():
    wid = _resolve_main_window_id()
    if not wid:
        print("[]")
        return

    try:
        out = subprocess.check_output(["python3", SKILL, "screenshot", "카카오톡", "--id", wid], stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
        obj = json.loads(out)
    except Exception:
        print("[]")
        return

    vision_rows = set()
    tesser_rows = set()

    # Vision OCR 숫자: 오른쪽 배지 영역만
    for e in obj.get("elements", []):
        t = str(e.get("text", "")).strip()
        x, y = e.get("at", [0, 0])
        if not (90 <= int(y) <= 950):
            continue
        if ":" in t:
            continue
        nums = [int(g) for g in re.findall(r"\d+", t) if g.isdigit()]
        if any(1 <= v <= 300 for v in nums) and int(x) >= 700:
            n = nearest_row(int(y))
            if n is not None:
                vision_rows.add(n)

    img_path = obj.get("file")
    if img_path and Path(img_path).exists():
        try:
            im = Image.open(img_path).convert("RGB")
            w, h = im.size
            for yy in Y_ROWS:
                y1, y2 = max(0, yy - 26), min(h - 1, yy + 26)
                x1, x2 = int(w * 0.83), int(w * 0.985)
                roi = im.crop((x1, y1, x2, y2)).convert("L")
                roi = roi.resize((roi.width * 3, roi.height * 3))
                roi = roi.point(lambda p: 255 if p > 150 else 0)

                txt = pytesseract.image_to_string(
                    roi,
                    config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789",
                )
                txt = re.sub(r"\D", "", txt or "")
                if not txt:
                    continue
                try:
                    v = int(txt)
                except Exception:
                    continue
                if 1 <= v <= 300:
                    tesser_rows.add(yy)
        except Exception:
            pass

    rows = sorted(vision_rows | tesser_rows)
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
