from .db import conn_ctx


def top_events(limit=30):
    with conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT event_type, vendor, product_name, room_name, created_at, old_price, new_price, stock_status
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    for r in rows:
        print(f"[{r['created_at']}] {r['event_type']} | {r['vendor'] or '-'} | {r['product_name'] or '-'} | {r['room_name']} | {r['old_price']}->{r['new_price']} | {r['stock_status']}")


if __name__ == "__main__":
    top_events()
