#!/usr/bin/env python3
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX = Path('/Users/sanghun/.openclaw/media/inbound/file_40---2c5d8262-b052-4262-8461-432fc0083de1.xlsx')
OUT = ROOT / 'data' / 'seller_product_terms_20260212.json'

STOP = {
    '공지','안내','긴급','상품','상품별','배송','출고','입고','인상','인하','특가','최고집','팜허브','전국','국내산',
    '실속형','선물용','가정용','비세척','세척','무료','추가','도서산간','제주도'
}
UNIT_PAT = re.compile(r'\b\d+(?:\.\d+)?\s?(?:kg|g|ml|l|L|개|과|봉|팩|망|박스|box|입)\b', re.I)


def norm(s:str)->str:
    return re.sub(r'[^0-9a-z가-힣]','',s.lower())


def extract_rows(xlsx: Path):
    z = zipfile.ZipFile(xlsx)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        ns = {'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for si in root.findall('a:si',ns):
            shared.append(''.join((t.text or '') for t in si.findall('.//a:t',ns)))

    wb = ET.fromstring(z.read('xl/workbook.xml'))
    ns = {'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    rid = wb.find('a:sheets/a:sheet', ns).attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    nsr = {'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
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
        name = (d.get('상품명') or '').strip()
        code = (d.get('관리코드') or '').strip()
        if name:
            out.append((code, name))
    return out


def main():
    rows = extract_rows(XLSX)
    terms = {}
    for _, name in rows:
        parts = [p.strip() for p in re.split(r'\s*/\s*', name) if p.strip()]
        canonical = parts[0] if parts else name
        canonical = re.sub(r'\s+', ' ', canonical).strip()

        cands = [canonical] + parts
        for c in cands:
            c = UNIT_PAT.sub(' ', c)
            c = re.sub(r'\([^)]*\)', ' ', c)
            c = re.sub(r'\s+', ' ', c).strip(' -')
            if not c or len(c) < 2:
                continue
            if c in STOP:
                continue
            if c.isdigit():
                continue
            if re.search(r'(공지|안내|배송|출고|입고|마감|인상|인하|특가)$', c):
                continue
            n = norm(c)
            if len(n) < 2:
                continue
            # longest canonical preference
            prev = terms.get(n)
            if not prev or len(canonical) > len(prev):
                terms[n] = canonical

    payload = {
        'generated_at': '2026-02-12',
        'source': XLSX.name,
        'term_count': len(terms),
        'terms': terms
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'written {OUT} terms={len(terms)}')


if __name__ == '__main__':
    main()
