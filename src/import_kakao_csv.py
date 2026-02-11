import csv
import sys
from pathlib import Path
from datetime import datetime

from .pipeline import ingest_line


def import_csv(path: Path, room_name: str):
    imported = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            created_at = (row.get("Date") or "").strip()
            sender = (row.get("User") or "unknown").strip() or "unknown"
            msg = (row.get("Message") or "").strip()
            if not msg:
                continue
            # csv has 'YYYY-MM-DD HH:MM:SS'
            try:
                ts = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
            except Exception:
                ts = datetime.now().isoformat(timespec="seconds")
            if ingest_line(room_name, msg, sender=sender, created_at=ts):
                imported += 1
    return imported


def infer_room_name(path: Path):
    stem = path.stem
    if "KakaoTalk_Chat_" in stem:
        stem = stem.split("KakaoTalk_Chat_", 1)[1]
    # trailing timestamp trim
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].count("-") >= 3:
        stem = parts[0]
    return stem.replace("_", " ").strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.import_kakao_csv <csv_path> [room_name]")
        sys.exit(1)

    p = Path(sys.argv[1]).expanduser()
    room = sys.argv[2] if len(sys.argv) >= 3 else infer_room_name(p)
    n = import_csv(p, room)
    print(f"imported={n} room={room}")
