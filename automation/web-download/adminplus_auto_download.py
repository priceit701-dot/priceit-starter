#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
SECRETS = BASE / "secrets"
SHEET_ROWS = SECRETS / "sheet_rows.json"
ART = BASE / "artifacts"
ART.mkdir(parents=True, exist_ok=True)
DL_DIR = BASE / "downloads"
DL_DIR.mkdir(parents=True, exist_ok=True)


def load_creds(site_name: str):
    data = json.loads(SHEET_ROWS.read_text(encoding="utf-8"))
    values = data.get("values", [])
    # rows like: [no, mall, '견적서', '링크', '어드민플러스', id, pw, note]
    for r in values:
        if len(r) >= 7 and site_name in r[1]:
            return {"site": r[1], "id": r[5], "pw": r[6], "note": r[7] if len(r) > 7 else ""}
    raise RuntimeError(f"No credentials row matched site_name={site_name}")


def newest_download_since(start_ts: float):
    d = DL_DIR
    cands = [p for p in d.glob("*") if p.is_file() and p.stat().st_mtime >= start_ts and re.search(r"\.(xlsx?|csv)$", p.name, re.I)]
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def direct_excel_export(page, site_slug='site'):
    endpoint = "?mod=product/excel&actpage=prt.excel.download.proc"
    url = urljoin(page.url, endpoint)
    resp = page.context.request.get(url, timeout=60000)
    if not resp.ok:
        return None, f"http-{resp.status}"

    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r"filename=\"?([^\";]+)\"?", cd)
    filename = m.group(1) if m else f"adminplus_export_{int(time.time())}.xlsx"
    filename = filename.replace('/', '_')
    out = DL_DIR / f"{site_slug}_{int(time.time())}_{filename}"
    out.write_bytes(resp.body())
    return out, None


def click_by_text(page, texts):
    for t in texts:
        loc = page.get_by_text(t, exact=False)
        try:
            n = loc.count()
        except Exception:
            n = 0
        for i in range(min(n, 5)):
            try:
                loc.nth(i).click(timeout=2000)
                return t
            except Exception:
                pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--site", default="팡이농장")
    ap.add_argument("--id", dest="uid", default=None)
    ap.add_argument("--pw", dest="upw", default=None)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    if args.uid and args.upw:
        creds = {"site": args.site, "id": args.uid, "pw": args.upw, "note": "manual"}
    else:
        creds = load_creds(args.site)
    start_ts = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, downloads_path=str(DL_DIR))
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        page.goto(args.url, wait_until="domcontentloaded")

        # login (robust selectors)
        page.wait_for_load_state("domcontentloaded")
        uid = page.locator('input[name="id"], input#id, input[placeholder*="아이디"], input[type="text"]')
        pwd = page.locator('input[name="pw"], input[name="password"], input[type="password"], input[placeholder*="비밀번호"]')
        if uid.count() == 0 or pwd.count() == 0:
            shot = ART / f"adminplus_selector_fail_{int(time.time())}.png"
            page.screenshot(path=str(shot), full_page=True)
            raise RuntimeError(f"login selectors not found. url={page.url} shot={shot}")
        uid.first.fill(creds["id"])
        pwd.first.fill(creds["pw"])

        btn = page.get_by_role("button", name="로그인")
        if btn.count() > 0:
            btn.first.click()
        else:
            page.locator('button:has-text("로그인"), input[type="submit"]').first.click()
        page.wait_for_timeout(3000)

        # direct + heuristic click for excel download
        clicked = None
        page.wait_for_timeout(1500)

        site_slug = re.sub(r'[^0-9A-Za-z가-힣_-]+','_', creds['site'])
        # stable path: authenticated direct export request
        dl, export_err = direct_excel_export(page, site_slug=site_slug)
        if dl:
            clicked = "direct-http-export"
        else:
            # fallback: page function / UI click
            try:
                ok = page.evaluate("() => (typeof excelDownLoad === 'function') ? (excelDownLoad(), true) : false")
                if ok:
                    clicked = "js:excelDownLoad()"
            except Exception:
                pass

            if not clicked:
                direct = page.locator('input[value*="엑셀 다운로드"], input[value*="전체제품"], button:has-text("엑셀 다운로드"), a:has-text("엑셀 다운로드")')
                if direct.count() > 0:
                    direct.first.click()
                    clicked = "direct:엑셀 다운로드"
                else:
                    keywords = ["전체제품 엑셀 다운로드", "견적서", "엑셀", "Excel", "다운로드", "내려받기", "파일다운로드"]
                    clicked = click_by_text(page, keywords)
            page.wait_for_timeout(5000)
            dl = newest_download_since(start_ts)

        shot = ART / f"adminplus_after_login_{int(time.time())}.png"
        page.screenshot(path=str(shot), full_page=True)
        out = {
            "site": creds["site"],
            "id": creds["id"],
            "clicked": clicked,
            "screenshot": str(shot),
            "downloaded": str(dl) if dl else None,
            "export_error": export_err if 'export_err' in locals() else None,
            "url": page.url,
        }
        rep = ART / "adminplus_last_run.json"
        rep.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
