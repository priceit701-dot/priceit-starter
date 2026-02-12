-- OpenChat outbox migration v1

CREATE TABLE IF NOT EXISTS openchat_priority_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_fact_id INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  next_retry_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  sent_at TEXT,
  FOREIGN KEY(event_fact_id) REFERENCES openchat_event_fact(id),
  UNIQUE(event_fact_id)
);

CREATE INDEX IF NOT EXISTS idx_openchat_priority_outbox_status_retry
ON openchat_priority_outbox(status, next_retry_at, created_at);
