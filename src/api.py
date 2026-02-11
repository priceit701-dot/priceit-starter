from typing import Optional
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .db import init_db
from .pipeline import ingest_line
from .config import DB_PATH

app = FastAPI(title="priceit collector")


class IngestBody(BaseModel):
    room_name: str
    message_text: str
    sender: str = "unknown"
    created_at: Optional[str] = None


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest")
def ingest(body: IngestBody):
    ok = ingest_line(body.room_name, body.message_text, body.sender, body.created_at)
    return {"ok": ok}


@app.get("/stats/summary")
def stats_summary():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("select count(*), max(created_at) from messages")
    msg_count, last_msg = cur.fetchone()
    cur.execute("select count(*) from events")
    ev_count = cur.fetchone()[0]
    cur.execute("select room_name, count(*) c from messages group by room_name order by c desc limit 20")
    top_rooms = [{"room": r, "count": c} for r, c in cur.fetchall()]
    cur.execute("select event_type, count(*) c from events group by event_type order by c desc")
    by_type = [{"type": t, "count": c} for t, c in cur.fetchall()]
    conn.close()
    return {
        "messages": msg_count,
        "events": ev_count,
        "last_message_at": last_msg,
        "top_rooms": top_rooms,
        "events_by_type": by_type,
    }


@app.get("/stats/timeline")
def stats_timeline(limit_hours: int = 48):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        select substr(created_at, 1, 13) || ':00:00' as hour_key, count(*)
        from messages
        where datetime(created_at) >= datetime('now', ?)
        group by hour_key
        order by hour_key asc
        """,
        (f"-{limit_hours} hours",),
    )
    timeline = [{"hour": h, "count": c} for h, c in cur.fetchall()]
    conn.close()
    return {"timeline": timeline}


@app.get("/stats/quality")
def stats_quality(limit_hours: int = 24):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        select event_type, count(*) c, round(avg(confidence), 3) avg_conf
        from events
        where datetime(created_at) >= datetime('now', ?)
        group by event_type
        order by c desc
        """,
        (f"-{limit_hours} hours",),
    )
    by_type = [
        {"event_type": t, "count": c, "avg_confidence": avg_conf}
        for t, c, avg_conf in cur.fetchall()
    ]
    cur.execute(
        """
        select reason, count(*) c
        from ingestion_audit
        where datetime(created_at) >= datetime('now', ?)
        group by reason
        order by c desc
        """,
        (f"-{limit_hours} hours",),
    )
    skips = [{"reason": r, "count": c} for r, c in cur.fetchall()]
    conn.close()
    return {"hours": limit_hours, "event_quality": by_type, "skip_reasons": skips}


@app.get("/events/recent")
def events_recent(limit: int = 30):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        select id, room_name, vendor, product_name, event_type, old_price, new_price, confidence, created_at
        from events
        order by id desc
        limit ?
        """,
        (min(max(limit, 1), 200),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"items": rows}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    html_path = Path(__file__).resolve().parent.parent / "web" / "dashboard.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>dashboard not found</h1>"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="0.0.0.0", port=8877, reload=False)
