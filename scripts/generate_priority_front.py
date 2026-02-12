#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db')
OUT = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/reports/openchat_priority_front_v1.html')


def esc(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        '''
        SELECT vendor_name, room_name, event_type, notice_subtype, importance_level, importance_score, event_at,
               substr(message_text,1,180) as message_snippet
        FROM v_openchat_priority_feed
        WHERE vendor_name IS NOT NULL
          AND room_name NOT LIKE 'bench_room_%'
        ORDER BY event_at DESC
        LIMIT 1200
        '''
    ).fetchall()

    vendors = sorted({r['vendor_name'] for r in rows if r['vendor_name']})

    tr = []
    for r in rows:
        tr.append(
            f"<tr data-vendor='{esc(r['vendor_name'])}' data-level='{esc(r['importance_level'])}'>"
            f"<td>{esc(r['event_at'])}</td>"
            f"<td>{esc(r['vendor_name'])}</td>"
            f"<td>{esc(r['room_name'])}</td>"
            f"<td>{esc(r['event_type'])}</td>"
            f"<td>{esc(r['notice_subtype'])}</td>"
            f"<td><b>{esc(r['importance_level'])}</b> ({round(r['importance_score'] or 0,1)})</td>"
            f"<td>{esc(r['message_snippet'])}</td>"
            "</tr>"
        )

    vendor_options = "".join([f"<option value='{esc(v)}'>{esc(v)}</option>" for v in vendors])

    html = f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>OpenChat Priority Front v1</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0b1020;color:#e5e7eb;margin:0;padding:16px}}
.wrap{{max-width:1400px;margin:0 auto}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px;margin-bottom:12px}}
label{{font-size:13px;color:#9ca3af}}
select,input{{background:#0f172a;color:#e5e7eb;border:1px solid #334155;border-radius:8px;padding:8px;margin-right:8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{border-bottom:1px solid #243041;padding:8px;vertical-align:top;text-align:left}}
th{{position:sticky;top:0;background:#111827}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px}}
.high{{background:#7f1d1d}} .medium{{background:#78350f}} .low{{background:#1f2937}}
</style>
</head>
<body>
<div class='wrap'>
  <div class='card'>
    <h2 style='margin:0 0 8px 0'>오픈채팅 우선순위 피드 (업체별 최신순)</h2>
    <div>
      <label>업체</label>
      <select id='vendor'><option value=''>전체</option>{vendor_options}</select>
      <label>중요도</label>
      <select id='level'>
        <option value=''>전체</option>
        <option value='high'>high</option>
        <option value='medium'>medium</option>
        <option value='low'>low</option>
      </select>
      <label>검색</label>
      <input id='q' placeholder='메시지/유형 검색' />
      <span id='cnt'></span>
    </div>
  </div>

  <div class='card' style='overflow:auto; max-height:75vh'>
    <table id='t'>
      <thead>
        <tr><th>시각</th><th>업체</th><th>룸</th><th>유형</th><th>세부유형</th><th>중요도</th><th>내용</th></tr>
      </thead>
      <tbody>
        {''.join(tr)}
      </tbody>
    </table>
  </div>
</div>
<script>
const vendor=document.getElementById('vendor');
const level=document.getElementById('level');
const q=document.getElementById('q');
const rows=[...document.querySelectorAll('#t tbody tr')];
const cnt=document.getElementById('cnt');
function f(){{
  let n=0;
  rows.forEach(r=>{{
    const okVendor=!vendor.value||r.dataset.vendor===vendor.value;
    const okLevel=!level.value||r.dataset.level===level.value;
    const okQ=!q.value||r.innerText.toLowerCase().includes(q.value.toLowerCase());
    const show=okVendor&&okLevel&&okQ;
    r.style.display=show?'':'none';
    if(show) n++;
  }});
  cnt.textContent=`표시 ${'{'}n{'}'}건`;
}}
[vendor,level,q].forEach(el=>el.addEventListener('input',f));
f();
</script>
</body>
</html>
"""
    OUT.write_text(html, encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
