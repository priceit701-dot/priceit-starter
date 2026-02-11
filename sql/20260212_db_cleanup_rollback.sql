-- phase1/phase2 롤백 초안
-- 주의: 운영 반영 전 반드시 백업 파일에서 복원 가능한지 점검할 것

BEGIN;

DROP VIEW IF EXISTS v_events_alarm;

DROP INDEX IF EXISTS idx_events_created_at;
DROP INDEX IF EXISTS idx_events_room_time;
DROP INDEX IF EXISTS idx_events_message_id;
DROP INDEX IF EXISTS idx_events_vendor_product;
DROP INDEX IF EXISTS idx_products_updated_at;

DROP INDEX IF EXISTS idx_room_aliases_std;
DROP INDEX IF EXISTS idx_vendor_aliases_std;
DROP INDEX IF EXISTS idx_product_aliases_std;

DROP INDEX IF EXISTS idx_events_v2_type_time;
DROP INDEX IF EXISTS idx_events_v2_room_time;
DROP INDEX IF EXISTS idx_events_v2_vendor_product;

DROP TABLE IF EXISTS events_v2;
DROP TABLE IF EXISTS event_type_map;
DROP TABLE IF EXISTS product_aliases_db;
DROP TABLE IF EXISTS vendor_aliases_db;
DROP TABLE IF EXISTS room_aliases;

COMMIT;
