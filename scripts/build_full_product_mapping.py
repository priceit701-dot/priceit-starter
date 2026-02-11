#!/usr/bin/env python3
import csv
import json
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
XLSX = Path('/Users/sanghun/.openclaw/media/inbound/file_40---2c5d8262-b052-4262-8461-432fc0083de1.xlsx')
DB = ROOT / 'data' / 'priceit.db'
OUT_JSON = ROOT / 'reports' / 'full_product_mapping_20260212.json'
OUT_CSV = ROOT / 'reports' / 'full_product_mapping_20260212.csv'
OUT_MD = ROOT / 'reports' / 'full_product_mapping_20260212.md'

CATEGORY_RULES = [
    ('과일', ['사과','배','감귤','딸기','레드향','천혜향','한라봉','참외','수박','멜론','키위','샤인머스켓','포도','자두','블루베리','토마토']),
    ('채소', ['양파','마늘','감자','고구마','상추','시금치','오이','배추','무','당근','구좌당근','버섯','표고','부추','깻잎','미나리','콜라비','비트']),
    ('쌀/잡곡', ['쌀','현미','찹쌀','잡곡','보리','귀리','수수','콩']),
    ('견과/건과', ['아몬드','호두','캐슈','피스타치오','견과','건과','곶감','건시','반건시']),
    ('수산물/건어물', ['꼬막','오징어','고등어','갈치','새우','멸치','건어물','수산']),
    ('축산/계란', ['한우','육우','돼지','삼겹','목살','소고기','닭','계란','달걀']),
    ('냉장/냉동/간편요리', ['만두','밀키트','간편조리','즉석','냉동','냉장']),
]

FOODSAFETY_HINT_RULES = [
    ('신선편의식품', ['샐러드','컷','손질']),
    ('즉석조리식품', ['밀키트','간편조리','조리세트']),
    ('즉석섭취식품', ['도시락','김밥','햄버거','즉석섭취']),
    ('만두류', ['만두']),
    ('과채가공품', ['주스','쥬스','착즙']),
    ('과일류', ['사과','배','감귤','딸기','포도','키위','참외','토마토']),
    ('채소류', ['양파','마늘','감자','고구마','상추','시금치','당근','배추','버섯']),
    ('견과류/건과류', ['아몬드','호두','견과','곶감','건시','반건시']),
]

GRADE_PAT = re.compile(r'(특품|특상|특|상|중|하|A\+?|B|C|프리미엄|로얄|선별|못난이|가정용)')
WEIGHT_PAT = re.compile(r'\b\d+(?:\.\d+)?\s?(?:kg|g|ml|l|L|개|과|봉|팩|망|박스|box|입)\b', re.I)
ORIGIN_PAT = re.compile(r'(국내산|국산|수입산|중국산|미국산|칠레산|제주|해남|밀양|고랭지|경남|전남|강원)')
PACK_PAT = re.compile(r'(실속형|선물용|소포장|대포장|개별포장|벌크|팩|봉|박스|망)')
STORAGE_PAT = re.compile(r'(냉장|냉동|상온|신선|산지직송|당일출고)')


def norm(s: str) -> str:
    return re.sub(r'[^0-9a-z가-힣]', '', (s or '').lower())


def pick_rule(name: str, rules):
    for label, kws in rules:
        if any(k in name for k in kws):
            return label
    return '미분류'


def extract_rows(xlsx: Path):
    z = zipfile.ZipFile(xlsx)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for si in root.findall('a:si', ns):
            shared.append(''.join((t.text or '') for t in si.findall('.//a:t', ns)))

    wb = ET.fromstring(z.read('xl/workbook.xml'))
    ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    rid = wb.find('a:sheets/a:sheet', ns).attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    nsr = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    target = None
    for rel in rels.findall('r:Relationship', nsr):
        if rel.attrib.get('Id') == rid:
            target = rel.attrib['Target']
            break
    sheet_path = 'xl/' + target if not target.startswith('xl/') else target
    root = ET.fromstring(z.read(sheet_path))

    def cell_val(c):
        t = c.attrib.get('t')
        v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
        if v is None:
            return ''
        x = v.text or ''
        if t == 's':
            try:
                return shared[int(x)]
            except Exception:
                return x
        return x

    rows = root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row')
    header = []
    out = []
    for i, r in enumerate(rows):
        vals = [cell_val(c) for c in r.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c')]
        if i == 0:
            header = vals
            continue
        if not vals:
            continue
        d = {header[j]: vals[j] if j < len(vals) else '' for j in range(len(header))}
        if (d.get('상품명') or '').strip():
            out.append(d)
    return out


def main():
    rows = extract_rows(XLSX)
    mapped = []
    for d in rows:
        code = (d.get('관리코드') or '').strip()
        name = (d.get('상품명') or '').strip()
        base = re.split(r'\s*/\s*', name)[0].strip()
        market_cat = pick_rule(name, CATEGORY_RULES)
        fs_hint = pick_rule(name, FOODSAFETY_HINT_RULES)
        grade = (GRADE_PAT.search(name).group(1) if GRADE_PAT.search(name) else '')
        weights = WEIGHT_PAT.findall(name)
        origin = (ORIGIN_PAT.search(name).group(1) if ORIGIN_PAT.search(name) else '')
        pack = (PACK_PAT.search(name).group(1) if PACK_PAT.search(name) else '')
        storage = (STORAGE_PAT.search(name).group(1) if STORAGE_PAT.search(name) else '')

        mapped.append({
            '관리코드': code,
            '상품명': name,
            '기준상품명': base,
            '마켓카테고리': market_cat,
            '식품안전유형힌트': fs_hint,
            '등급': grade,
            '규격': '|'.join(weights),
            '산지': origin,
            '포장': pack,
            '보관': storage,
            'norm_key': norm(base or name),
        })

    # save db table
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS seller_product_mapping (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          product_code TEXT,
          product_name TEXT,
          base_name TEXT,
          market_category TEXT,
          foodsafety_hint TEXT,
          grade TEXT,
          unit_text TEXT,
          origin TEXT,
          pack TEXT,
          storage TEXT,
          norm_key TEXT,
          updated_at TEXT
        )
    ''')
    cur.execute('DELETE FROM seller_product_mapping')
    now = datetime.now().isoformat(timespec='seconds')
    cur.executemany('''
        INSERT INTO seller_product_mapping
        (product_code, product_name, base_name, market_category, foodsafety_hint, grade, unit_text, origin, pack, storage, norm_key, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    ''', [
        (
            x['관리코드'], x['상품명'], x['기준상품명'], x['마켓카테고리'], x['식품안전유형힌트'], x['등급'], x['규격'], x['산지'], x['포장'], x['보관'], x['norm_key'], now
        ) for x in mapped
    ])
    conn.commit()
    conn.close()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        'generated_at': now,
        'rows': len(mapped),
        'mapped': mapped,
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(mapped[0].keys()))
        writer.writeheader()
        writer.writerows(mapped)

    # summary
    from collections import Counter
    cat_counter = Counter(x['마켓카테고리'] for x in mapped)
    fs_counter = Counter(x['식품안전유형힌트'] for x in mapped)
    md = [
        '# 전체 상품 매핑 결과 (2026-02-12)',
        '',
        f'- 총 상품행: **{len(mapped)}**',
        f'- DB 테이블 적재: `seller_product_mapping`',
        '',
        '## 마켓카테고리 분포',
    ]
    for k, v in cat_counter.most_common():
        md.append(f'- {k}: {v}')
    md += ['', '## 식품안전유형 힌트 분포']
    for k, v in fs_counter.most_common():
        md.append(f'- {k}: {v}')

    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(f'written {OUT_JSON}\nwritten {OUT_CSV}\nwritten {OUT_MD}\nrows={len(mapped)}')


if __name__ == '__main__':
    main()
