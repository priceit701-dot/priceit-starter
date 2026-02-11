import sqlite3
from contextlib import contextmanager
from .config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_name TEXT NOT NULL,
  sender TEXT,
  message_text TEXT NOT NULL,
  raw_line TEXT,
  created_at TEXT NOT NULL,
  hash TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS ingestion_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  line_hash TEXT NOT NULL,
  reason TEXT NOT NULL,
  raw_line TEXT
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor TEXT NOT NULL,
  product_name TEXT NOT NULL,
  canonical_key TEXT UNIQUE,
  latest_price INTEGER,
  last_stock_status TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL,
  room_name TEXT NOT NULL,
  vendor TEXT,
  product_name TEXT,
  event_type TEXT NOT NULL,
  old_price INTEGER,
  new_price INTEGER,
  stock_status TEXT,
  confidence REAL DEFAULT 0.0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_room_time ON messages(room_name, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_room_line_time ON messages(room_name, message_text, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ingestion_audit_time ON ingestion_audit(created_at);
"""


@contextmanager
def conn_ctx():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with conn_ctx() as conn:
        conn.executescript(SCHEMA_SQL)
