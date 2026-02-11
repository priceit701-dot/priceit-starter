from typing import Optional
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import init_db
from .pipeline import ingest_line
from .config import DB_PATH

app = FastAPI(title="priceit collector")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALERT_TYPES_ORDER = [
    "PRICE_UP",
    "PRICE_DOWN",
    "SOLD_OUT",
    "RESTOCK",
    "DELAY_NOTICE",
    "NEW_ITEM",
    "NOTICE",
]
ACTION_REQUIRED_TYPES = ["SOLD_OUT", "DELAY_NOTICE", "PRICE_UP", "PRICE_DOWN"]


class IngestBody(BaseModel):
    room_name: str
    message_text: str
    sender: str = "unknown"
    created_at: Optional[str] = None


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
if WEB_ROOT.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_ROOT)), name="web")


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


@app.get("/stats/seller")
def stats_seller(limit_hours: int = 24, feed_limit: int = 30, action_limit: int = 15):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(ALERT_TYPES_ORDER))
    cur.execute(
        f"""
        select event_type, count(*) c
        from events
        where datetime(created_at) >= datetime('now', ?)
          and event_type in ({placeholders})
        group by event_type
        """,
        [f"-{limit_hours} hours", *ALERT_TYPES_ORDER],
    )
    counts = {row["event_type"]: row["c"] for row in cur.fetchall()}
    today_alerts = [{"type": alert_type, "count": int(counts.get(alert_type, 0))} for alert_type in ALERT_TYPES_ORDER]

    cur.execute(
        """
        select id, room_name, vendor, product_name, event_type, old_price, new_price, confidence, created_at
        from events
        where event_type in ({})
        order by id desc
        limit ?
        """.format(placeholders),
        [*ALERT_TYPES_ORDER, min(max(feed_limit, 1), 100)],
    )
    recent_feed = [dict(r) for r in cur.fetchall()]

    action_placeholders = ",".join(["?"] * len(ACTION_REQUIRED_TYPES))
    cur.execute(
        """
        select id, room_name, vendor, product_name, event_type, old_price, new_price, confidence, created_at
        from events
        where event_type in ({})
        order by id desc
        limit ?
        """.format(action_placeholders),
        [*ACTION_REQUIRED_TYPES, min(max(action_limit, 1), 100)],
    )
    action_items = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "hours": limit_hours,
        "alert_types_order": ALERT_TYPES_ORDER,
        "today_alert_summary": today_alerts,
        "recent_alert_feed": recent_feed,
        "action_required_types": ACTION_REQUIRED_TYPES,
        "action_required_items": action_items,
    }


@app.get("/stats/control-tower")
def stats_control_tower(limit_hours: int = 24):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("select count(*), max(created_at) from messages")
    message_count, last_message_at = cur.fetchone()

    cur.execute(
        """
        select room_name, count(*) c
        from messages
        where datetime(created_at) >= datetime('now', ?)
        group by room_name
        order by c desc
        limit 10
        """,
        (f"-{limit_hours} hours",),
    )
    top_room_traffic = [dict(r) for r in cur.fetchall()]

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
    skip_reasons = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        select count(*)
        from ingestion_audit
        where datetime(created_at) >= datetime('now', ?)
          and reason like 'error:%'
        """,
        (f"-{limit_hours} hours",),
    )
    error_count = cur.fetchone()[0]

    cur.execute(
        """
        select count(*)
        from events
        where datetime(created_at) >= datetime('now', '-1 hours')
        """
    )
    events_last_hour = cur.fetchone()[0]

    if not last_message_at:
        pipeline_status = "DOWN"
        pipeline_desc = "최근 메시지가 없어 파이프라인 입력을 확인해야 합니다."
    elif events_last_hour == 0:
        pipeline_status = "WARN"
        pipeline_desc = "최근 1시간 이벤트가 없습니다. 수집 또는 파싱 상태를 점검하세요."
    else:
        pipeline_status = "OK"
        pipeline_desc = "최근 1시간 이벤트가 확인되어 파이프라인이 동작 중입니다."

    conn.close()
    return {
        "hours": limit_hours,
        "kpi": {
            "messages": int(message_count or 0),
            "last_message_at": last_message_at,
            "events_last_hour": int(events_last_hour or 0),
            "ingestion_errors": int(error_count or 0),
        },
        "data_quality": {
            "skip_reasons": skip_reasons,
            "error_count": int(error_count or 0),
        },
        "top_room_traffic": top_room_traffic,
        "pipeline_status": {
            "status": pipeline_status,
            "description": pipeline_desc,
        },
    }


def _serve_html(file_name: str):
    html_path = WEB_ROOT / file_name
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return f"<h1>{file_name} not found</h1>"


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return _serve_html("dashboard.html")


@app.get("/dashboard_v1.html", response_class=HTMLResponse)
def dashboard_v1():
    return _serve_html("dashboard_v1.html")


@app.get("/dashboard_v2.html", response_class=HTMLResponse)
def dashboard_v2():
    return _serve_html("dashboard_v2.html")


@app.get("/dashboard_v3.html", response_class=HTMLResponse)
def dashboard_v3():
    return _serve_html("dashboard_v3.html")


@app.get("/dashboard_v4.html", response_class=HTMLResponse)
def dashboard_v4():
    return _serve_html("dashboard_v4.html")


@app.get("/dashboard_v5.html", response_class=HTMLResponse)
def dashboard_v5():
    return _serve_html("dashboard_v5.html")


@app.get("/admin/control-tower", response_class=HTMLResponse)
def admin_control_tower():
    return _serve_html("admin_control_tower.html")


@app.get("/admin/seller", response_class=HTMLResponse)
def admin_seller():
    return _serve_html("admin_seller.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="0.0.0.0", port=8877, reload=False)
