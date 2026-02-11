# Dedup Audit Report (20260212)

- DB: `/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db`
- Executed at: 2026-02-12T06:13:34.340033
- Apply mode: `true`
- Backup file: `-`

## Duplicate Definitions
- **messages**: 중복 정의: room_name + sender(NULL→'') + message_text + created_at가 동일한 레코드
- **events**: 중복 정의: message_id + event_type + vendor(NULL→'') + product_name(NULL→'') + created_at가 동일한 레코드
- **products**: 중복 정의: canonical_key(공백/NULL 제외)가 동일한 레코드
- **alarm_summary**: 중복 정의: v_events_alarm 기준 room_name + event_type_std + vendor_std(NULL→'') + product_std(NULL→'') + created_at + message_id(NULL→-1)가 동일한 이벤트

## Before/After Duplicate Counts

| Target | Before groups | Before rows | After groups | After rows |
|---|---:|---:|---:|---:|
| messages | 0 | 0 | 0 | 0 |
| events | 0 | 0 | 0 | 0 |
| products | 0 | 0 | 0 | 0 |
| alarm_summary | 0 | 0 | 0 | 0 |

## Alarm Type Impact (Before → After)

| event_type_std | before | after | delta |
|---|---:|---:|---:|
| DELAY_NOTICE | 101 | 101 | +0 |
| NEW_ITEM | 112 | 112 | +0 |
| NOTICE | 356 | 356 | +0 |
| PRICE_DOWN | 366 | 366 | +0 |
| PRICE_UP | 40 | 40 | +0 |
| RESTOCK | 629 | 629 | +0 |
| SOLD_OUT | 236 | 236 | +0 |

## Rollback

- Restore command: `No-op (no changes applied)`
