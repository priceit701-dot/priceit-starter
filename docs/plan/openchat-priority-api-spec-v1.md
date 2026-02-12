# OpenChat Priority API Spec v1

## Endpoint
- `POST {PRICEIT_PRIORITY_API_URL}`

## Headers
- `Content-Type: application/json`
- `Authorization: Bearer {PRICEIT_PRIORITY_API_TOKEN}` (optional)

## Payload
```json
{
  "event_fact_id": 123,
  "event_type": "DELAY_NOTICE",
  "notice_subtype": "DELIVERY_DELAY",
  "room_name": "팜허브 오픈채팅",
  "vendor_name": "팜허브",
  "old_price": 12000,
  "new_price": 13000,
  "importance_level": "high",
  "importance_score": 92,
  "is_actionable": 1,
  "event_at": "2026-02-12T20:12:00",
  "message_text": "배송지연 안내..."
}
```

## Expected response
- 2xx: accepted/saved
- non-2xx: sender will retry with backoff

## Retry policy
- 1st fail: +1m
- 2nd fail: +5m
- 3rd fail: +15m
- 4th+ fail: +60m cap

## Sender scripts
- enqueue: `scripts/enqueue_priority_outbox.py`
- push: `scripts/push_priority_outbox.py`

## Recommended server behavior
1. idempotency key: `event_fact_id`
2. upsert by event_fact_id
3. return 200/201 on duplicate (already processed)
