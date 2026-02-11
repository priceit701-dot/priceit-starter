#!/usr/bin/env python3
import csv
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

DOWNLOADS = Path('/Users/sanghun/Downloads')
OUT = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/docs/openchat-export-review.md')


def classify(msg: str):
    m = msg.strip()
    if '님이 들어왔습니다' in m:
        return 'JOIN'
    if '님이 나갔습니다' in m:
        return 'LEAVE'
    if '공지' in m:
        return 'NOTICE'
    if '품절' in m:
        return 'SOLD_OUT'
    if '인상' in m:
        return 'PRICE_UP'
    if '인하' in m or '특가' in m:
        return 'PRICE_DOWN_OR_PROMO'
    if '신규' in m or '재오픈' in m:
        return 'NEW_ITEM'
    if '지연' in m or '출고' in m or '택배' in m:
        return 'DELIVERY'
    return 'OTHER'


def main():
    files = sorted(DOWNLOADS.glob('KakaoTalk_Chat_*.csv'))
    total_rows = 0
    by_type = Counter()
    by_hour = Counter()
    by_file = {}

    for fp in files:
        c = 0
        with fp.open('r', encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f)
            for row in rd:
                msg = (row.get('Message') or '').strip()
                dt = (row.get('Date') or '').strip()
                if not msg:
                    continue
                total_rows += 1
                c += 1
                by_type[classify(msg)] += 1
                try:
                    h = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:00')
                    by_hour[h] += 1
                except Exception:
                    pass
        by_file[fp.name] = c

    lines = []
    lines.append('# 오픈채팅 Export 복기\n')
    lines.append(f'- 파일 수: {len(files)}')
    lines.append(f'- 총 메시지 행: {total_rows}\n')

    lines.append('## 파일별 건수')
    for k, v in sorted(by_file.items(), key=lambda x: x[1], reverse=True):
        lines.append(f'- {k}: {v}')

    lines.append('\n## 유형별 건수')
    for k, v in by_type.most_common():
        lines.append(f'- {k}: {v}')

    lines.append('\n## 시간순(상위 20시간대)')
    for h, c in sorted(by_hour.items(), key=lambda x: x[1], reverse=True)[:20]:
        lines.append(f'- {h}: {c}')

    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'written={OUT}')


if __name__ == '__main__':
    main()
