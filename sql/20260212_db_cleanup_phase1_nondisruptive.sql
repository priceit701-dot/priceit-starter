-- 목적: 운영 중 무중단으로 적용 가능한 정리 기반 구조 추가
-- 주의: 기존 테이블/컬럼/데이터를 삭제하거나 변경하지 않음

BEGIN;

-- 1) 표준화 보조 차원 테이블
CREATE TABLE IF NOT EXISTS room_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_name_raw TEXT NOT NULL UNIQUE,
  room_name_std TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS vendor_aliases_db (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_raw TEXT NOT NULL UNIQUE,
  vendor_std TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS product_aliases_db (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_raw TEXT NOT NULL,
  product_std TEXT NOT NULL,
  canonical_key_std TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  UNIQUE(product_raw, product_std)
);

-- 2) 알람 타입 정합성 매핑(운영 중 추가 가능)
CREATE TABLE IF NOT EXISTS event_type_map (
  event_type_raw TEXT PRIMARY KEY,
  event_type_std TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'normal',
  is_alert INTEGER NOT NULL DEFAULT 1,
  is_supported INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT
);

INSERT OR IGNORE INTO event_type_map(event_type_raw, event_type_std, severity, is_alert, is_supported)
VALUES
('PRICE_UP', 'PRICE_UP', 'high', 1, 1),
('PRICE_DOWN', 'PRICE_DOWN', 'normal', 1, 1),
('SOLD_OUT', 'SOLD_OUT', 'high', 1, 1),
('RESTOCK', 'RESTOCK', 'normal', 1, 1),
('DELAY_NOTICE', 'DELAY_NOTICE', 'high', 1, 1),
('NEW_ITEM', 'NEW_ITEM', 'normal', 1, 1),
('NOTICE', 'NOTICE', 'low', 1, 1),
-- 현행 데이터에 존재하는 비표준 타입은 지원/비지원 명시
('PRICE_SEEN', 'NOTICE', 'low', 0, 0),
('SOLD_OUT_RISK', 'SOLD_OUT', 'high', 1, 0);

-- 3) 현행 데이터 기반 초기 alias seed (raw=std)
INSERT OR IGNORE INTO room_aliases(room_name_raw, room_name_std)
SELECT DISTINCT room_name, trim(room_name)
FROM messages
WHERE room_name IS NOT NULL AND trim(room_name) != '';

INSERT OR IGNORE INTO vendor_aliases_db(vendor_raw, vendor_std)
SELECT DISTINCT vendor, trim(vendor)
FROM events
WHERE vendor IS NOT NULL AND trim(vendor) != '';

INSERT OR IGNORE INTO product_aliases_db(product_raw, product_std)
SELECT DISTINCT product_name, trim(product_name)
FROM events
WHERE product_name IS NOT NULL AND trim(product_name) != '';

-- 4) 조회 성능 및 검증 쿼리 대응 인덱스
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_room_time ON events(room_name, created_at);
CREATE INDEX IF NOT EXISTS idx_events_message_id ON events(message_id);
CREATE INDEX IF NOT EXISTS idx_events_vendor_product ON events(vendor, product_name);
CREATE INDEX IF NOT EXISTS idx_products_updated_at ON products(updated_at);

CREATE INDEX IF NOT EXISTS idx_room_aliases_std ON room_aliases(room_name_std);
CREATE INDEX IF NOT EXISTS idx_vendor_aliases_std ON vendor_aliases_db(vendor_std);
CREATE INDEX IF NOT EXISTS idx_product_aliases_std ON product_aliases_db(product_std);

-- 5) 알람 전용 정규화 뷰(애플리케이션 즉시 사용 가능)
CREATE VIEW IF NOT EXISTS v_events_alarm AS
SELECT
  e.id,
  e.message_id,
  e.room_name,
  COALESCE(ra.room_name_std, trim(e.room_name)) AS room_name_std,
  e.vendor AS vendor_raw,
  CASE
    WHEN e.vendor LIKE '____-__-__T__:%' THEN NULL
    ELSE COALESCE(va.vendor_std, trim(e.vendor))
  END AS vendor_std,
  e.product_name AS product_raw,
  CASE
    WHEN e.product_name LIKE '____-__-__T__:%' THEN NULL
    ELSE COALESCE(pa.product_std, trim(e.product_name))
  END AS product_std,
  COALESCE(etm.event_type_std, e.event_type) AS event_type_std,
  etm.severity,
  etm.is_alert,
  etm.is_supported,
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
