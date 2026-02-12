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
    # 우선순위: 메인 목록창(제목=카카오톡) > 로그인창 > 첫 카카오창
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "카카오톡":
            return str(w.get("id"))
    for w in arr:
        if w.get("app") == "카카오톡" and w.get("title") == "로그인":
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

    rows = set()

    # A) OCR elements from Vision (existing)
    for e in obj.get("elements", []):
        t = str(e.get("text", "")).strip()
        x, y = e.get("at", [0, 0])
        if not (90 <= int(y) <= 950):
            continue
        if ":" in t:
            continue
        nums = [int(g) for g in re.findall(r"\d+", t) if g.isdigit()]
        if any(1 <= v <= 300 for v in nums) and int(x) >= 560:
            n = nearest_row(int(y))
            if n is not None:
                rows.add(n)

    img_path = obj.get("file")
    if img_path and Path(img_path).exists():
        try:
            im = Image.open(img_path).convert("RGB")
            w, h = im.size

            # B) red bubble color detection (row anchored)
            x1, x2 = int(w * 0.70), int(w * 0.98)
            for yy in Y_ROWS:
                y1, y2 = max(0, yy - 34), min(h - 1, yy + 34)
                red = 0
                for y in range(y1, y2 + 1, 2):
                    for x in range(x1, x2 + 1, 2):
                        r, g, b = im.getpixel((x, y))
                        if r > 180 and g < 130 and b < 130 and (r - g) > 50 and (r - b) > 50:
                            red += 1
                if red >= 16:
                    rows.add(yy)

            # C) Tesseract fallback on right-side row ROI (D mode)
            for yy in Y_ROWS:
                y1, y2 = max(0, yy - 30), min(h - 1, yy + 30)
                x1, x2 = int(w * 0.75), int(w * 0.97)
                roi = im.crop((x1, y1, x2, y2)).convert("L")
                txt = pytesseract.image_to_string(
                    roi,
                    config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789",
                )
                txt = re.sub(r"\D", "", txt or "")
                if txt:
                    try:
                        v = int(txt)
                    except Exception:
                        continue
                    if 1 <= v <= 300:
                        rows.add(yy)
        except Exception:
            pass

    print(json.dumps(sorted(rows)))


if __name__ == "__main__":
    main()
