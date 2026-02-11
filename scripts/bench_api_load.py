#!/usr/bin/env python3
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api import app
from src.db import init_db


def percentile(values, p):
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


async def run_worker(client, worker_id, requests_per_worker, latencies_ms, errors, slow_logs, slow_ms):
    for i in range(requests_per_worker):
        payload = {
            "room_name": f"bench_room_{worker_id % 8}",
            "message_text": f"[{datetime.now().isoformat(timespec='seconds')}] 농산물 특가 {random.randint(1000, 9999)}원",
            "sender": "bench",
            "created_at": datetime.now().isoformat(timespec='seconds'),
        }
        t0 = time.perf_counter()
        try:
            r = await client.post("/ingest", json=payload)
            dt_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(dt_ms)
            if r.status_code != 200:
                errors.append({"worker": worker_id, "idx": i, "status": r.status_code, "body": r.text[:120]})
            if dt_ms >= slow_ms:
                slow_logs.append({"worker": worker_id, "idx": i, "latency_ms": round(dt_ms, 2)})
        except Exception as e:
            dt_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(dt_ms)
            errors.append({"worker": worker_id, "idx": i, "error": str(e)})


async def bench(total_requests, concurrency, slow_ms):
    init_db()
    latencies_ms = []
    errors = []
    slow_logs = []

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bench.local") as client:
        per_worker = total_requests // concurrency
        remainder = total_requests % concurrency

        tasks = []
        for w in range(concurrency):
            n = per_worker + (1 if w < remainder else 0)
            tasks.append(run_worker(client, w, n, latencies_ms, errors, slow_logs, slow_ms))

        t0 = time.perf_counter()
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - t0

    latencies_ms.sort()
    success = total_requests - len(errors)
    out = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "total_requests": total_requests,
        "concurrency": concurrency,
        "elapsed_sec": round(elapsed, 3),
        "throughput_rps": round(total_requests / elapsed, 2) if elapsed > 0 else 0,
        "success": success,
        "errors": len(errors),
        "error_rate": round(len(errors) / total_requests, 4) if total_requests else 0,
        "latency_ms": {
            "avg": round(statistics.mean(latencies_ms), 2) if latencies_ms else 0,
            "p50": round(percentile(latencies_ms, 0.50), 2),
            "p95": round(percentile(latencies_ms, 0.95), 2),
            "p99": round(percentile(latencies_ms, 0.99), 2),
            "max": round(max(latencies_ms), 2) if latencies_ms else 0,
        },
        "bottleneck_logs": slow_logs[:100],
        "error_logs": errors[:50],
    }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--slow-ms", type=float, default=25.0)
    parser.add_argument("--out", default="docs/bench/v6-local-bench.json")
    args = parser.parse_args()

    result = asyncio.run(bench(args.requests, args.concurrency, args.slow_ms))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("BENCH_DONE")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
