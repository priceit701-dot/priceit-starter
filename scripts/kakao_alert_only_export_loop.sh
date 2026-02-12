#!/bin/zsh
set -euo pipefail

SKILL="/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py"
MAIN_ID=""
LOG="/Users/sanghun/.openclaw/workspace/priceit-starter/logs/kakao_alert_only_export_loop.log"
STATE="/Users/sanghun/.openclaw/workspace/priceit-starter/logs/kakao_alert_only_state.json"
TOP_FALLBACK_Y=120

# verified click line coordinates (openchat list)
X=520
Y_LIST=(120 236 350 465 580 696 812 928)

# verified settings coordinates
SETTINGS_MENU_X=95
SETTINGS_MENU_Y=300
SAVE_BTN_X=380
SAVE_BTN_Y=365

INTERVAL=60
ONCE=0
# 엄격 모드: 빨간 배지 감지 시에만 접근
ALL_WHEN_EMPTY=0
DEDUP_WINDOW_SEC=600
LAST_FILE_STATE="/Users/sanghun/.openclaw/workspace/priceit-starter/logs/kakao_alert_only_last_file.txt"
LAST_ROOM_STATE="/Users/sanghun/.openclaw/workspace/priceit-starter/logs/kakao_alert_only_last_room.txt"
LAST_ROOM_TS_STATE="/Users/sanghun/.openclaw/workspace/priceit-starter/logs/kakao_alert_only_last_room_ts.txt"
[[ "${1:-}" == "--once" ]] && ONCE=1

mkdir -p "$(dirname "$LOG")"

resolve_main_id() {
  python3 - <<'PY'
import json,subprocess
arr=json.loads(subprocess.check_output(['python3','/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py','list']).decode())
for w in arr:
    if w.get('app')=='카카오톡' and w.get('title') in ('카카오톡','로그인',''):
        print(w.get('id'))
        break
PY
}

settings_window_id() {
  python3 - <<'PY'
import json,subprocess
arr=json.loads(subprocess.check_output(['python3','/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py','list']).decode())
for w in arr:
    if w.get('app')=='카카오톡' and w.get('title')=='Window':
        print(w.get('id'))
        break
PY
}

current_room_title() {
  python3 - <<'PY'
import json,subprocess
arr=json.loads(subprocess.check_output(['python3','/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py','list']).decode())
for w in arr:
    if w.get('app')=='카카오톡' and w.get('title') not in ('카카오톡','Window'):
        print(w.get('title'))
        break
PY
}

latest_kakao_file_after() {
  local start_ts="$1"
  python3 - "$start_ts" <<'PY'
import sys,time
from pathlib import Path
start=int(sys.argv[1])
home=Path.home()
roots=[home/'Downloads',home/'Documents',home/'Desktop',home/'Library'/'Containers']
cand=[]
for r in roots:
    if not r.exists(): continue
    for p in r.rglob('*'):
        if not p.is_file(): continue
        n=p.name.lower()
        if ('kakaotalk' in n or 'chat_' in n or '오픈채팅' in n or '톡' in n) and p.suffix.lower() in {'.csv','.txt'}:
            try: st=p.stat(); mt=int(st.st_mtime)
            except: continue
            if mt>=start: cand.append((mt,str(p),st.st_size))

cand.sort(reverse=True)
if cand:
    mt,p,s=cand[0]
    print(f"{mt}\t{s}\t{p}")
PY
}

alert_rows_json() {
  python3 - <<'PY'
import json,subprocess,re
Y=[120,236,350,465,580,696,812,928]
cmd=['python3','/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py','screenshot','카카오톡']
out=subprocess.check_output(cmd).decode('utf-8','ignore')
obj=json.loads(out)
rows=set()
for e in obj.get('elements',[]):
    t=str(e.get('text','')).strip()
    x,y=e.get('at',[0,0])
    # unread badge OCR(강한 트리거): 오픈채팅 목록 각 방 우측의 빨간 숫자만 사용
    # 제외: 좌측 카카오 로고 배지, 상단 채팅/오픈채팅 탭 배지
    has_digit = any(ch.isdigit() for ch in t)
    has_colon = ':' in t
    short_like = len(t) <= 4
    in_room_list_y = 90 <= int(y) <= 950
    if has_digit and (not has_colon) and short_like and int(x)>=680 and in_room_list_y:
        nearest=min(Y,key=lambda yy:abs(yy-int(y)))
        if abs(nearest-int(y))<=45:
            rows.add(nearest)
print(json.dumps(sorted(rows)))
PY
}

top_signature() {
  python3 - <<'PY'
import json,subprocess,re
cmd=['python3','/Users/sanghun/.openclaw/workspace/skills/mac-use/scripts/mac_use.py','screenshot','카카오톡']
out=subprocess.check_output(cmd).decode('utf-8','ignore')
obj=json.loads(out)
# top row signature from elements near first row region
parts=[]
for e in obj.get('elements',[]):
    t=str(e.get('text','')).strip()
    x,y=e.get('at',[0,0])
    if 70 <= int(y) <= 170 and 300 <= int(x) <= 760:
        if t:
            parts.append(t)
print(' | '.join(parts[:4]))
PY
}

export_one_row() {
  local y="$1"
  local last_room="$2"

  python3 "$SKILL" key --app 카카오톡 cmd+w >/dev/null 2>&1 || true
  sleep 0.2
  python3 "$SKILL" key --app 카카오톡 cmd+w >/dev/null 2>&1 || true
  sleep 0.3

  python3 "$SKILL" click --app 카카오톡 --id "$MAIN_ID" "$X" "$y" >/dev/null 2>&1 || true
  python3 "$SKILL" key --app 카카오톡 return >/dev/null 2>&1 || true
  sleep 0.8

  local room
  room="$(current_room_title || true)"
  if [[ -n "$room" && "$room" == "$last_room" ]]; then
    local y2=$((y+18))
    python3 "$SKILL" key --app 카카오톡 cmd+w >/dev/null 2>&1 || true
    sleep 0.2
    python3 "$SKILL" click --app 카카오톡 --id "$MAIN_ID" "$X" "$y2" >/dev/null 2>&1 || true
    python3 "$SKILL" key --app 카카오톡 return >/dev/null 2>&1 || true
    sleep 0.8
    room="$(current_room_title || true)"
  fi

  local start_ts
  start_ts=$(date +%s)

  python3 "$SKILL" key --app 카카오톡 opt+cmd+, >/dev/null 2>&1 || true
  sleep 0.8
  local sid
  sid="$(settings_window_id || true)"
  if [[ -n "$sid" ]]; then
    python3 "$SKILL" click --app 카카오톡 --id "$sid" "$SETTINGS_MENU_X" "$SETTINGS_MENU_Y" >/dev/null 2>&1 || true
    sleep 0.35
    python3 "$SKILL" click --app 카카오톡 --id "$sid" "$SAVE_BTN_X" "$SAVE_BTN_Y" >/dev/null 2>&1 || true
    sleep 0.7
  fi

  python3 "$SKILL" key --app 카카오톡 return >/dev/null 2>&1 || true
  sleep 0.35
  python3 "$SKILL" key --app 카카오톡 return >/dev/null 2>&1 || true
  sleep 0.8

  local newf
  newf="$(latest_kakao_file_after "$start_ts" || true)"
  if [[ -n "$newf" ]]; then
    local new_path
    new_path="$(echo "$newf" | awk -F'\t' '{print $3}')"
    local last_path=""
    [[ -f "$LAST_FILE_STATE" ]] && last_path="$(cat "$LAST_FILE_STATE" 2>/dev/null || true)"

    local now_ts
    now_ts=$(date +%s)
    local prev_room=""
    local prev_room_ts=0
    [[ -f "$LAST_ROOM_STATE" ]] && prev_room="$(cat "$LAST_ROOM_STATE" 2>/dev/null || true)"
    [[ -f "$LAST_ROOM_TS_STATE" ]] && prev_room_ts="$(cat "$LAST_ROOM_TS_STATE" 2>/dev/null || echo 0)"

    # 중복 방지: 같은 파일 경로 반복 또는 같은 방을 짧은 시간 내 반복 수집하면 DUP로 처리
    if [[ -n "$new_path" && "$new_path" == "$last_path" ]]; then
      echo "[$(date '+%F %T')] DUP y=$y room=$room file=$newf" >> "$LOG"
    elif [[ -n "$room" && "$room" == "$prev_room" && $((now_ts-prev_room_ts)) -lt $DEDUP_WINDOW_SEC ]]; then
      echo "[$(date '+%F %T')] DUP_WINDOW y=$y room=$room file=$newf" >> "$LOG"
    else
      echo "$new_path" > "$LAST_FILE_STATE"
      echo "$room" > "$LAST_ROOM_STATE"
      echo "$now_ts" > "$LAST_ROOM_TS_STATE"
      echo "[$(date '+%F %T')] OK y=$y room=$room file=$newf" >> "$LOG"
    fi
  else
    echo "[$(date '+%F %T')] MISS y=$y room=$room file=NONE" >> "$LOG"
  fi

  python3 "$SKILL" key --app 카카오톡 cmd+w >/dev/null 2>&1 || true
  sleep 0.2
  python3 "$SKILL" key --app 카카오톡 cmd+w >/dev/null 2>&1 || true
  sleep 0.2

  echo "$room"
}

echo "[$(date '+%F %T')] start alert-only export loop" >> "$LOG"
last_room=""

while true; do
  MAIN_ID="$(resolve_main_id || true)"
  if [[ -z "$MAIN_ID" ]]; then
    echo "[$(date '+%F %T')] WARN main_window_id_not_found" >> "$LOG"
    [[ $ONCE -eq 1 ]] && break
    sleep "$INTERVAL"
    continue
  fi
  rows_json="$(alert_rows_json || echo '[]')"
  top_sig="$(top_signature || true)"
  last_sig=""
  [[ -f "$STATE" ]] && last_sig="$(cat "$STATE" 2>/dev/null || true)"

  # 엄격 모드: 빨간 배지 감지가 없으면 접근하지 않음

  echo "$top_sig" > "$STATE"
  echo "[$(date '+%F %T')] alert_rows=$rows_json" >> "$LOG"

  for y in $(python3 - <<PY
import json
arr=json.loads('''$rows_json''')
for x in arr: print(x)
PY
); do
    last_room="$(export_one_row "$y" "$last_room")"
  done

  [[ $ONCE -eq 1 ]] && break
  sleep "$INTERVAL"
done

echo "[$(date '+%F %T')] finish alert-only export loop" >> "$LOG"
