-- 목적: 점진적 마이그레이션용 정규화 이벤트 팩트 테이블 초안
-- 전략: 기존 events 유지 + events_v2 병행 적재/검증 후 전환

BEGIN;

CREATE TABLE IF NOT EXISTS events_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  legacy_event_id INTEGER UNIQUE,
  message_id INTEGER NOT NULL,
  room_name_std TEXT NOT NULL,
  vendor_std TEXT,
  product_std TEXT,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'PRICE_UP','PRICE_DOWN','SOLD_OUT','RESTOCK','DELAY_NOTICE','NEW_ITEM','NOTICE'
  )),
  old_price INTEGER,
  new_price INTEGER,
  stock_status TEXT,
  confidence REAL NOT NULL DEFAULT 0.0,
  created_at TEXT NOT NULL,
  migrated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_events_v2_type_time ON events_v2(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_events_v2_room_time ON events_v2(room_name_std, created_at);
CREATE INDEX IF NOT EXISTS idx_events_v2_vendor_product ON events_v2(vendor_std, product_std);

-- 1차 백필: 비표준 타입을 event_type_map 기준으로 표준화
--        vendor/product timestamp 오염값은 NULL 처리
INSERT OR IGNORE INTO events_v2(
  legacy_event_id,
  message_id,
  room_name_std,
  vendor_std,
  product_std,
  event_type,
  old_price,
  new_price,
  stock_status,
  confidence,
  created_at
)
SELECT
  e.id,
  e.message_id,
  COALESCE(ra.room_name_std, trim(e.room_name)) AS room_name_std,
  CASE WHEN e.vendor LIKE '____-__-__T__:%' THEN NULL ELSE COALESCE(va.vendor_std, trim(e.vendor)) END AS vendor_std,
  CASE WHEN e.product_name LIKE '____-__-__T__:%' THEN NULL ELSE COALESCE(pa.product_std, trim(e.product_name)) END AS product_std,
  COALESCE(etm.event_type_std, 'NOTICE') AS event_type,
  e.old_price,
  e.new_price,
  e.stock_status,
  e.confidence,
  e.created_at
FROM events e
LEFT JOIN room_aliases ra ON ra.room_name_raw = e.room_name
LEFT JOIN vendor_aliases_db va ON va.vendor_raw = e.vendor
LEFT JOIN product_aliases_db pa ON pa.product_raw = e.product_name
LEFT JOIN event_type_map etm ON etm.event_type_raw = e.event_type;

COMMIT;
