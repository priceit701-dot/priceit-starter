import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "priceit.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("select count(*) from messages")
messages = cur.fetchone()[0]
cur.execute("select count(*) from events")
events = cur.fetchone()[0]
cur.execute("select reason, count(*) from ingestion_audit group by reason order by count(*) desc")
audit = cur.fetchall()
cur.execute("""
select count(*)
from (
  select room_name, message_text, created_at, count(*) c
  from messages
  group by room_name, message_text, created_at
  having c > 1
) t
""")
exact_dups = cur.fetchone()[0]

print("V1_METRICS messages=", messages)
print("V1_METRICS events=", events)
print("V1_METRICS exact_duplicate_keys=", exact_dups)
print("V1_METRICS audit_top=", audit[:5])

conn.close()
