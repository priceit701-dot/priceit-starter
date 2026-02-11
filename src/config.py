from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("DB_PATH", "./data/priceit.db"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
KAKAO_ROOM_NAME = os.getenv("KAKAO_ROOM_NAME", "오픈채팅")
COLLECT_INTERVAL_SEC = int(os.getenv("COLLECT_INTERVAL_SEC", "20"))
