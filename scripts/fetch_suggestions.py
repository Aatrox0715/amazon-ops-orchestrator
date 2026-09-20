#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取 Amazon 搜索框下拉建议（L2 关键词扩展手段）

原理：Amazon 有公开的 autocomplete 接口，返回真实用户的搜索输入建议。
在没有第三方工具账号（拿不到搜索量）的条件下，这是最接近真实搜索需求的词源。

用法：
  python fetch_suggestions.py --project <代号> [--seeds "a,b,c"] [--market US]

--seeds 省略时，会尝试从项目 02/03 环节的产出里自动提取种子词。

产出：
  <项目>/04-关键词库/raw/suggestions.json
"""
import argparse
import gzip
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ── 统一配置（三级回退，替代硬编码路径）──
try:
    from _config import project_root, coach_dir, SKILL_ROOT
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from _config import project_root, coach_dir, SKILL_ROOT


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = project_root()
STAGE_DIR = "04-关键词库"
TZ = timezone(timedelta(hours=8))

HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://www.amazon.com/",
    "X-Requested-With": "XMLHttpRequest",
}

MARKET = {
    "US": {"mid": "ATVPDKIKX0DER", "lop": "en_US", "host": "completion.amazon.com", "mkt": "1"},
    "UK": {"mid": "A1F83G8C2ARO7P", "lop": "en_GB", "host": "completion.amazon.co.uk", "mkt": "3"},
    "DE": {"mid": "A1PA6795UKMFR9", "lop": "de_DE", "host": "completion.amazon.de", "mkt": "4"},
}


def fetch_json(url, retries=2):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HDR)
            r = urllib.request.urlopen(req, timeout=30, context=ctx)
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(1.5 + i)
    raise last


def suggest(term, market="US"):
    """返回该词的下拉建议列表"""
    m = MARKET.get(market, MARKET["US"])
    q = urllib.parse.quote(term)

    # 主接口（新版）
    url1 = (
        "https://{host}/api/2017/suggestions"
        "?limit=11&prefix={q}&suggestion-type=KEYWORD&page-type=Gateway"
        "&alias=aps&site-variant=desktop&version=3&event=onKeyPress"
        "&mid={mid}&lop={lop}&last-prefix={q}&avg-ks-time=0&fb=1"
        "&plain-mid=1&client-info=amazon-search-ui"
    ).format(host=m["host"], q=q, mid=m["mid"], lop=m["lop"])

    try:
        d = fetch_json(url1)
        out = [s.get("value") for s in (d.get("suggestions") or []) if s.get("value")]
        if out:
            return out, "api2017"
    except Exception:
        pass

    # 回退接口（旧版）
    url2 = (
        "https://{host}/search/complete"
        "?search-alias=aps&client=amazon-search-ui&mkt={mkt}&q={q}"
    ).format(host=m["host"], mkt=m["mkt"], q=q)
    try:
        d = fetch_json(url2)
        if isinstance(d, list) and len(d) > 1:
            return [x for x in d[1] if isinstance(x, str)], "legacy"
    except Exception:
        pass

    return [], "failed"


def read_seeds_from_project(project):
    """从 02/03 环节产出里提取种子词"""
    seeds = []
    p2 = os.path.join(ROOT, project, "02-竞品拆解", "output.json")
    if os.path.isfile(p2):
        try:
            d = json.load(open(p2, encoding="utf-8"))
            pl = d.get("payload", {})
            seeds += (pl.get("copy_strategy", {}).get("covered_keywords_from_frontend") or [])[:6]
            bc = pl.get("target_asins", [{}])[0].get("breadcrumb") or []
            if bc:
                seeds.append(bc[-1])
        except Exception:
            pass
    p3 = os.path.join(ROOT, project, "03-评论与VOC分析", "output.json")
    if os.path.isfile(p3):
        try:
            d = json.load(open(p3, encoding="utf-8"))
            lang = d.get("payload", {}).get("buyer_language", {})
            seeds += (lang.get("scenario_words") or [])[:3]
        except Exception:
            pass
    # 去重、去过长词组、清洗
    seen, out = set(), []
    for s in seeds:
        s = (s or "").strip().lower()
        if not s or len(s) > 60 or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--market", default="US")
    args = ap.parse_args()

    if args.seeds:
        seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    else:
        seeds = read_seeds_from_project(args.project)
    if not seeds:
        print("没有种子词。请用 --seeds \"a,b,c\" 指定。", file=sys.stderr)
        sys.exit(1)

    print(f"种子词（{len(seeds)} 个）: {seeds}")
    print(f"站点: {args.market}\n")

    result = {}
    for s in seeds:
        words, via = suggest(s, args.market)
        result[s] = {"via": via, "suggestions": words}
        print(f"[{via:8s}] {s:36s} → {len(words)} 条")
        for w in words[:12]:
            print(f"            · {w}")
        print()
        time.sleep(0.8)

    outdir = os.path.join(ROOT, args.project, STAGE_DIR, "raw")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "suggestions.json")
    allw = sorted({w for v in result.values() for w in v["suggestions"]})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "market": args.market,
            "fetched_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "data_path": "L2",
            "origin": "Amazon 搜索框 autocomplete 接口",
            "source_grade": "S4",
            "note": "反映热门搜索，不含低搜索量长尾；无搜索量/竞争度数值",
            "seed_count": len(seeds),
            "unique_suggestion_count": len(allw),
            "by_seed": result,
            "all_suggestions": allw,
        }, f, ensure_ascii=False, indent=2)

    print(f"合计去重建议词：{len(allw)} 条")
    print(f"已保存 → {out}")


if __name__ == "__main__":
    main()
