# DB Cleanup Apply Report (20260212)

- Status: **ok**
- Executed at: 2026-02-12T06:04:11.793203
- Step `backup`: ok
- Step `phase1_apply`: ok
- Step `phase2_apply`: ok

## Alarm 7-type ordered counts
- PRICE_UP: 40
- PRICE_DOWN: 366
- SOLD_OUT: 236
- RESTOCK: 629
- DELAY_NOTICE: 101
- NEW_ITEM: 112
- NOTICE: 356

## Pre/Post Summary
- messages_rows: pre=37694 / post=37694
- events_rows: pre=1840 / post=1840
- products_rows: pre=1115 / post=1115
- events_vendor_ts_like: pre=327 / post=327
- events_product_ts_like: pre=327 / post=327
- events_v2_rows: 1840
- events_v2_vendor_std_null: 1494
- events_v2_product_std_null: 487

## Data quality reduction
- vendor timestamp-like contamination: 327 -> 0 (reduced 327)
- product timestamp-like contamination: 327 -> 0 (reduced 327)
- non-standard event types: 7 -> 0 (reduced 7)

## Rollback guide
- backup_file: `/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db.backup_20260212_060411`
- restore_command: `cp '/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db.backup_20260212_060411' '/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db'`
- sql_rollback_file: `/Users/sanghun/.openclaw/workspace/priceit-starter/sql/20260212_db_cleanup_rollback.sql`
