from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("DB_PATH", "./data/priceit.db"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
KAKAO_ROOM_NAME = os.getenv("KAKAO_ROOM_NAME", "오픈채팅")
COLLECT_INTERVAL_SEC = int(os.getenv("COLLECT_INTERVAL_SEC", "20"))
ROOMS_PER_CYCLE = int(os.getenv("ROOMS_PER_CYCLE", "50"))
ROOM_SWITCH_DELAY_SEC = float(os.getenv("ROOM_SWITCH_DELAY_SEC", "0.7"))
# 사용자 작업 간섭 완화: 일정 시간 유휴일 때만 수집
COLLECT_ONLY_WHEN_IDLE_SEC = float(os.getenv("COLLECT_ONLY_WHEN_IDLE_SEC", "8"))
# 클릭 기반 방 순회 좌표(카카오 좌측 목록)
ROOM_LIST_X = int(os.getenv("ROOM_LIST_X", "190"))
ROOM_LIST_Y_START = int(os.getenv("ROOM_LIST_Y_START", "330"))
ROOM_LIST_Y_STEP = int(os.getenv("ROOM_LIST_Y_STEP", "86"))
