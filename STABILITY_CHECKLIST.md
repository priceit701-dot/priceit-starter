# Kakao 수집 안정화 검증 체크리스트

## 실행 커맨드
```bash
cd /Users/sanghun/.openclaw/workspace/priceit-starter
./scripts/start_services.sh
./scripts/verify_stability.sh
```

## 수동 점검 항목
- [ ] `pgrep -fl 'src.api|src.kakao_clipboard_collector|scripts/watchdog.sh'` 결과가 프로세스당 1개인지 확인
- [ ] `logs/watchdog.log`에 동일한 `down -> restart`가 15초마다 반복되지 않는지 확인
- [ ] `logs/collector.log`에 `collector focus warning:` 발생 시 잘못된 앱으로 키 입력이 전송되지 않았는지 확인
- [ ] KakaoTalk를 포그라운드로 두었을 때 `cycle stats` 로그가 증가하는지 확인
- [ ] 클립보드가 수집 후 원래 값으로 복구되는지 확인

## 장애 시 빠른 확인
```bash
# pid/로그 확인
cat logs/api.pid logs/collector.pid logs/watchdog.pid

tail -n 50 logs/watchdog.log
tail -n 50 logs/collector.log
tail -n 50 logs/api.log
```
