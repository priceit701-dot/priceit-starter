-- OpenChat priority migration v1

ALTER TABLE openchat_event_fact ADD COLUMN notice_subtype TEXT;
ALTER TABLE openchat_event_fact ADD COLUMN effective_at TEXT;
ALTER TABLE openchat_event_fact ADD COLUMN importance_score REAL DEFAULT 0;
ALTER TABLE openchat_event_fact ADD COLUMN importance_level TEXT DEFAULT 'low' CHECK (importance_level IN ('high','medium','low'));
ALTER TABLE openchat_event_fact ADD COLUMN is_actionable INTEGER DEFAULT 0;
ALTER TABLE openchat_event_fact ADD COLUMN dedup_key TEXT;
ALTER TABLE openchat_event_fact ADD COLUMN processed_at TEXT;

CREATE TABLE IF NOT EXISTS event_priority_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_fact_id INTEGER NOT NULL,
  rule_version TEXT NOT NULL,
  score_before REAL,
  score_after REAL,
  level_after TEXT,
  reason TEXT,
  processed_at TEXT NOT NULL,
  FOREIGN KEY(event_fact_id) REFERENCES openchat_event_fact(id)
);

CREATE INDEX IF NOT EXISTS idx_openchat_event_fact_importance ON openchat_event_fact(importance_level, importance_score, event_at);
CREATE INDEX IF NOT EXISTS idx_openchat_event_fact_vendor_time ON openchat_event_fact(vendor_name, event_at);

CREATE VIEW IF NOT EXISTS v_openchat_priority_feed AS
SELECT
  f.id,
  f.room_name,
  f.vendor_name,
  f.event_type,
  f.notice_subtype,
  f.old_price,
  f.new_price,
  f.importance_level,
  f.importance_score,
  f.is_actionable,
  f.event_at,
  m.message_text
FROM openchat_event_fact f
LEFT JOIN messages m ON m.id = f.message_id
ORDER BY f.event_at DESC;
