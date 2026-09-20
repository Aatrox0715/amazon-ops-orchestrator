#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取并解析 Amazon listing 页面（L2 数据源手段）

用法：
  python fetch_listing.py <ASIN> --project <代号> [--market US] [--stage 02]

产出：
  <项目目录>/<环节目录>/raw/<ASIN>.html    原始页面（存档，供复核）
  <项目目录>/<环节目录>/raw/<ASIN>.json    解析后的结构化字段
  同时把 JSON 打到 stdout

设计原则：
  - 拿不到的字段写 null，绝不编造（配合 L3 标注）
  - raw HTML 必须存档：报告里的每个数字都能回溯到原始页面
"""
import gzip
import json
import os
import re
import ssl
import sys
import time
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
TZ = timezone(timedelta(hours=8))

HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

DOMAIN = {"US": "www.amazon.com", "UK": "www.amazon.co.uk",
          "DE": "www.amazon.de", "JP": "www.amazon.co.jp"}


# ---------- 抓取 ----------

def fetch(url, retries=2):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HDR)
            r = urllib.request.urlopen(req, timeout=40, context=ctx)
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "ignore"), r.status
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(2 + i * 2)
    raise last


# ---------- 解析辅助 ----------

def clean(s):
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
         .replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", s).strip() or None


def g(pat, h, flags=re.S):
    m = re.search(pat, h, flags)
    return clean(m.group(1)) if m else None


def gnum(s):
    if not s:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", s.replace(",", ""))
    if not m:
        return None
    v = m.group(0)
    return float(v) if "." in v else int(v)


def detect_block(h):
    """检测是否被反爬拦或页面无效"""
    low = h.lower()
    if "enter the characters you see below" in low or "api-services-support@amazon.com" in low:
        return "captcha"
    if "dogs of amazon" in low:
        return "dogpage"
    if 'id="producttitle"' not in low:
        return "no_product_title"
    return None


# ---------- 主解析 ----------

def parse(h, asin, market):
    out = {"asin": asin, "marketplace": market, "fetched_at": None, "blocked": None}

    b = detect_block(h)
    if b:
        out["blocked"] = b
        return out

    out["title"] = g(r'id="productTitle"[^>]*>(.*?)</span>', h)
    out["brand_byline"] = g(r'id="bylineInfo"[^>]*>(.*?)</a>', h)
    out["seller_byline"] = g(r'id="sellerProfileTriggerId"[^>]*>(.*?)</a>', h)

    # 价格：a-price-whole（整数）+ a-price-fraction（小数）
    whole = g(r'a-price-whole">\s*([\d,]+)', h)
    frac = g(r'a-price-fraction">\s*(\d{2})', h)
    if whole:
        out["price_usd"] = gnum(whole) + (int(frac) / 100 if frac else 0)
        out["price_raw"] = f"${whole}.{frac or '00'}"
    else:
        out["price_usd"] = None
        out["price_raw"] = None

    # 评分：title="4.6 out of 5 stars"
    out["rating"] = gnum(g(r'([\d.]+)\s*out of 5 stars', h))
    # 评论数：aria-label="117 Reviews"（比标签内文本可靠 —— 标签内是 "(117)" 带括号）
    out["review_count"] = gnum(g(r'aria-label="([\d,]+)\s*Reviews?"', h))
    out["answered_questions"] = gnum(g(r'([\d,]+)\s*answered questions', h))

    # 可售状态
    out["availability"] = g(r'id="availability"[\s\S]{0,400}?<span[^>]*>(.*?)</span>', h)
    out["buybox_seller"] = g(r'id="sellerProfileTriggerId"[^>]*>(.*?)</a>', h)
    # 卖家信息：用 offer-display-feature 的专属类名，比 "Ships from" 文本匹配可靠得多
    out["ships_from"] = g(
        r'desktop-fulfiller-info[\s\S]{0,400}?offer-display-feature-text-message">\s*([^<]+)<', h)
    out["sold_by"] = g(
        r'desktop-merchant-info[\s\S]{0,500}?offer-display-feature-text-message">\s*([^<]+)<', h)

    # 五点描述：主区域 featurebullets_feature_div（注意不是连字符），fallback 到 pqv-feature-bullets
    fb = None
    for pat in [r'id="featurebullets_feature_div"([\s\S]{0,9000}?)</div>\s*</div>',
                r'id="pqv-feature-bullets"([\s\S]{0,9000}?)</ul>']:
        fb = re.search(pat, h)
        if fb:
            break
    bullets = []
    if fb:
        for x in re.findall(r'<span class="a-list-item">\s*([\s\S]*?)\s*</span>', fb.group(1)):
            c = clean(x)
            if c and "See more" not in c and "Hide" not in c and len(c) > 20:
                bullets.append(c)
    out["feature_bullets"] = bullets or None

    # 后台关键词字段（页面通常不显示，标注为拿不到）
    out["search_terms"] = None
    out["search_terms_note"] = "后台 Search Terms 不在前台页面暴露，L3"

    # BSR
    bsr_m = re.search(r"Best Sellers Rank[\s\S]{0,800}?</table>", h) or \
            re.search(r"Best Sellers Rank[\s\S]{0,600}?</ul>", h) or \
            re.search(r"Best Sellers Rank([\s\S]{0,500})", h)
    if bsr_m:
        txt = clean(bsr_m.group(0)) or clean(bsr_m.group(1))
        ranks = re.findall(r"#([\d,]+)\s*in\s*([^#(]*?)(?=\(|#|$)", txt or "")
        out["bsr"] = [{"rank": gnum(r), "category": c.strip(" ,")}
                      for r, c in ranks if c.strip(" ,")][:6] or None
        out["bsr_raw"] = (txt or "")[:300]
    else:
        out["bsr"] = None
        out["bsr_raw"] = None

    out["date_first_available"] = g(r'Date First Available[\s\S]{0,200}?<span[^>]*>([^<]+)</span>', h)

    # 类目面包屑
    bc = re.search(r'id="wayfinding-breadcrumbs_feature_div"([\s\S]{0,2500}?)</div>', h)
    if bc:
        cr = re.findall(r'<a[^>]*class="a-link-normal[^"]*"[^>]*>([\s\S]*?)</a>', bc.group(1))
        out["breadcrumb"] = [clean(x) for x in cr if clean(x)] or None
    else:
        out["breadcrumb"] = None

    # 变体：只统计 twister（变体选择器）区域内的 ASIN。
    # ⚠️ 页面上还有其他 ASIN（推荐位、广告位），全页去重会严重高估变体数。
    tw = re.search(r'id="twister([\s\S]{0,8000})', h)
    v_asins = sorted(set(re.findall(r'"(B0[0-9A-Z]{8})"', tw.group(1)))) if tw else []
    out["has_variants"] = bool(v_asins)
    out["variant_count"] = len(v_asins) or None
    out["variant_asins"] = v_asins or None
    out["variant_axes"] = list(set(
        re.findall(r'"variationDisplayLabels"\s*:\s*\{([^}]{0,200})\}', h)
    ))[:3] or None
    out["variant_note"] = "仅统计变体选择器内 ASIN；页面其他 ASIN 属推荐位，不计入"

    # 主图 / 图片数
    out["main_image"] = g(r'"hiRes"\s*:\s*"(https://[^"]+)"', h) or \
                        g(r'id="landingImage"[^>]*src="([^"]+)"', h)
    out["image_count"] = len(set(re.findall(r'"hiRes"\s*:\s*"(https://[^"]+)"', h))) or None

    # A+ 内容
    out["has_a_plus"] = bool(re.search(r"aplus-module|premium-aplus", h))

    # 评分分布：aria-label="84 percent of reviews have 5 stars"（新 React 直方图组件唯一可靠模式）
    dist = {}
    for pct, star in re.findall(r'aria-label="(\d{1,3}) percent of reviews have (\d) stars?"', h):
        dist[star] = int(pct)
    total = sum(dist.values()) if dist else 0
    if dist and 98 <= total <= 102:
        out["rating_dist_pct"] = dist
        out["rating_dist_sum"] = total
    else:
        # 加总不接近 100% → 抓到的是残缺/错位数据，宁缺勿错
        out["rating_dist_pct"] = None
        out["rating_dist_note"] = f"L3：直方图解析加总异常（{total}%），已丢弃不用"

    # 是否含视频
    out["has_video"] = bool(re.search(r"videoBlock|vse-player|video-block", h))

    # 卖家类型推断线索（标注为推断）
    out["seller_type_hint"] = None
    if out["brand_byline"] and "Visit the" in h[:h.find("bylineInfo") + 200]:
        out["seller_type_hint"] = "疑似品牌备案卖家（有品牌店铺链接）"

    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asin = sys.argv[1].strip().upper()

    def opt(flag, default):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return default

    project = opt("--project", asin)
    market = opt("--market", "US").upper()
    stage = opt("--stage", "02")

    stage_dir = {"01": "01-市场调研", "02": "02-竞品拆解"}.get(stage, "02-竞品拆解")
    outdir = os.path.join(ROOT, project, stage_dir, "raw")
    os.makedirs(outdir, exist_ok=True)

    domain = DOMAIN.get(market, DOMAIN["US"])
    url = f"https://{domain}/dp/{asin}?th=1&psc=1"

    raw_path = os.path.join(outdir, f"{asin}.html")
    if "--reparse" in sys.argv and os.path.isfile(raw_path):
        # 复用已存档的 raw HTML 重新解析：改解析规则时无需重新抓取，也避免反复请求被限流
        print(f"复用已存 raw：{raw_path}")
        with open(raw_path, encoding="utf-8") as f:
            html = f.read()
    else:
        print(f"抓取 {url} ...")
        html, status = fetch(url)
        print(f"HTTP {status}，{len(html)} 字符")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(html)

    data = parse(html, asin, market)
    data["fetched_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    data["source_url"] = url
    data["raw_html_path"] = raw_path
    data["data_source_level"] = "L2"
    data["origin"] = "前台 listing 页抓取"

    if data.get("blocked"):
        print(f"⚠️ 页面被拦或无效：{data['blocked']}", file=sys.stderr)
        print(f"   raw 已存档：{raw_path}", file=sys.stderr)

    json_path = os.path.join(outdir, f"{asin}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"raw  → {raw_path}")
    print(f"json → {json_path}")
    print()
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
