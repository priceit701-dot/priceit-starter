# v6 Local Bench (2026-02-12)

## 실행 환경
- Host: priceit의 Mac mini (Darwin arm64)
- Command:
  - `TELEGRAM_BOT_TOKEN='' TELEGRAM_CHAT_ID='' python3 scripts/bench_api_load.py --requests 120 --concurrency 8 --slow-ms 20`
- Output JSON: `docs/bench/v6-local-bench.json`

## 결과 요약
- total_requests: 120
- concurrency: 8
- elapsed_sec: 0.146
- throughput_rps: 820.26
- errors: 0 (error_rate 0.0)
- latency(ms): avg 5.75 / p50 1.08 / p95 14.94 / p99 93.93 / max 128.32

## 병목 로그(임계 20ms 이상)
초기 워커 구간에서 스파이크 확인:
- worker=2 idx=0 latency=69.98ms
- worker=5 idx=0 latency=78.68ms
- worker=0 idx=1 latency=97.51ms
- worker=6 idx=0 latency=128.32ms

해석(관측 기반):
- 전 구간 오류는 없었고, 초기 burst에서만 고지연이 나타남.
- 병목 로그는 `bottleneck_logs`로 JSON에도 저장됨.
