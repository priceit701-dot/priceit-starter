from fastapi import FastAPI
from pydantic import BaseModel
from .db import init_db
from .pipeline import ingest_line

app = FastAPI(title="priceit collector")


class IngestBody(BaseModel):
    room_name: str
    message_text: str
    sender: str = "unknown"
    created_at: str | None = None


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="0.0.0.0", port=8877, reload=False)
