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

-- openchat painpoint redesign (2026-02-12)
CREATE TABLE IF NOT EXISTS openchat_item_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_item_key TEXT NOT NULL UNIQUE,
  vendor_name TEXT,
  product_name_raw TEXT,
  product_name_norm TEXT NOT NULL,
  coupang_category_l1 TEXT,
  coupang_category_l2 TEXT,
  item_type_hint TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS openchat_item_option (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL,
  option_name_raw TEXT,
  option_name_norm TEXT NOT NULL,
  unit TEXT,
  spec_value REAL,
  pack_count INTEGER,
  weight_gram INTEGER,
  FOREIGN KEY(item_id) REFERENCES openchat_item_master(id),
  UNIQUE(item_id, option_name_norm)
);

CREATE TABLE IF NOT EXISTS openchat_event_fact (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  legacy_event_id INTEGER UNIQUE,
  message_id INTEGER,
  room_name TEXT NOT NULL,
  vendor_name TEXT,
  item_id INTEGER NOT NULL,
  option_id INTEGER,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'PRICE_UP','PRICE_DOWN','SOLD_OUT','RESTOCK','DELAY_NOTICE','NEW_ITEM','NOTICE'
  )),
  old_price INTEGER,
  new_price INTEGER,
  stock_status TEXT,
  confidence REAL NOT NULL DEFAULT 0.0,
  event_at TEXT NOT NULL,
  FOREIGN KEY(message_id) REFERENCES messages(id),
  FOREIGN KEY(item_id) REFERENCES openchat_item_master(id),
  FOREIGN KEY(option_id) REFERENCES openchat_item_option(id)
);

CREATE INDEX IF NOT EXISTS idx_openchat_item_vendor_name ON openchat_item_master(vendor_name, product_name_norm);
CREATE INDEX IF NOT EXISTS idx_openchat_option_item ON openchat_item_option(item_id, option_name_norm);
CREATE INDEX IF NOT EXISTS idx_openchat_event_fact_time ON openchat_event_fact(event_at);
CREATE INDEX IF NOT EXISTS idx_openchat_event_fact_type_time ON openchat_event_fact(event_type, event_at);
CREATE INDEX IF NOT EXISTS idx_openchat_event_fact_item_time ON openchat_event_fact(item_id, option_id, event_at);
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
