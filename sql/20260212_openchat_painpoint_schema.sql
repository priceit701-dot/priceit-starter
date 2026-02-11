-- 2026-02-12: OpenChat DB painpoint redesign (product/option centric)
-- 핵심: 상태어보다 실상품명/옵션 중심 모델 + 7종 이벤트 표준화

BEGIN;

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

-- backfill item master from legacy products/events
INSERT OR IGNORE INTO openchat_item_master(
  canonical_item_key, vendor_name, product_name_raw, product_name_norm, first_seen_at, last_seen_at
)
SELECT
  COALESCE(NULLIF(trim(COALESCE(p.vendor, e.vendor, 'UNKNOWN')), ''), 'UNKNOWN') || '|' ||
  COALESCE(NULLIF(trim(COALESCE(p.product_name, e.product_name, m.message_text)), ''), '미분류 상품') AS canonical_item_key,
  COALESCE(NULLIF(trim(COALESCE(p.vendor, e.vendor)), ''), 'UNKNOWN') AS vendor_name,
  COALESCE(NULLIF(trim(COALESCE(p.product_name, e.product_name, m.message_text)), ''), '미분류 상품') AS product_name_raw,
  COALESCE(NULLIF(trim(COALESCE(p.product_name, e.product_name, m.message_text)), ''), '미분류 상품') AS product_name_norm,
  MIN(COALESCE(e.created_at, p.updated_at, m.created_at)) AS first_seen_at,
  MAX(COALESCE(e.created_at, p.updated_at, m.created_at)) AS last_seen_at
FROM events e
LEFT JOIN messages m ON m.id = e.message_id
LEFT JOIN products p ON p.vendor = e.vendor AND p.product_name = e.product_name
GROUP BY 1,2,3,4;

-- backfill event fact (non-standard types => NOTICE)
INSERT OR IGNORE INTO openchat_event_fact(
  legacy_event_id, message_id, room_name, vendor_name, item_id, option_id,
  event_type, old_price, new_price, stock_status, confidence, event_at
)
SELECT
  e.id,
  e.message_id,
  e.room_name,
  COALESCE(NULLIF(trim(e.vendor), ''), 'UNKNOWN') AS vendor_name,
  im.id,
  NULL,
  CASE
    WHEN e.event_type IN ('PRICE_UP','PRICE_DOWN','SOLD_OUT','RESTOCK','DELAY_NOTICE','NEW_ITEM','NOTICE')
      THEN e.event_type
    ELSE 'NOTICE'
  END AS event_type,
  e.old_price,
  e.new_price,
  e.stock_status,
  COALESCE(e.confidence, 0.0),
  e.created_at
FROM events e
LEFT JOIN messages m ON m.id = e.message_id
JOIN openchat_item_master im
  ON im.canonical_item_key = (
    COALESCE(NULLIF(trim(COALESCE(e.vendor, 'UNKNOWN')), ''), 'UNKNOWN') || '|' ||
    COALESCE(NULLIF(trim(COALESCE(e.product_name, m.message_text)), ''), '미분류 상품')
  );

COMMIT;
