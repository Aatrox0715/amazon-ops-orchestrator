#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Amazon Listing 文案合规自检

校验项（基于 2026-07-27 生效规范，S1）：
  1. 标题 ≤75 字符
  2. 商品亮点 ≤125 字符
  3. 五点：每条 10–255 字符，共 ≤5 条，总字节 ≤1000
  4. 后台 Search Terms ≤250 bytes
  5. 禁用字符：! $ ? _ { } ^ ¬ ¦
  6. 同词重复不超 2 次（介词/冠词/连词除外）
  7. 禁用话术：保证类、主观比较类、促销类

用法：
  python listing_check.py --json <文案.json>

文案 json 结构：
{
  "title": "...",
  "item_highlights": "...",       # 可选
  "bullets": ["...", "..."],
  "search_terms": "..."           # 可选
}
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TZ = timezone(timedelta(hours=8))

LIMITS = {
    "title_chars": 75,
    "highlights_chars": 125,
    "bullet_min_chars": 10,
    "bullet_max_chars": 255,
    "bullet_total_bytes": 1000,
    "search_terms_bytes": 250,
}

FORBIDDEN_CHARS = ["!", "$", "?", "_", "{", "}", "^", "¬", "¦"]
FORBIDDEN_CHARS_NOTE = "品牌名内部允许下划线，其余一律禁用"

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "with", "on", "at",
    "by", "from", "as", "is", "are", "be", "this", "that", "your", "you",
}

# 禁用话术（正则）
FORBIDDEN_PHRASES = {
    "保证类": r"\b(guarantee[ds]?|warranty|money[- ]back|refund|100% safe)\b",
    "主观比较类": r"\b(best[- ]?sell\w*|#1|no\.?\s?1|top[- ]?rated|most popular|"
                  r"eco[- ]?friendly|antimicrobial|smartest|cheapest)\b",
    "促销类": r"\b(free shipping|on sale|discount|clearance|buy now|limited time)\b",
    # ⚠️ 注意：cure / treat 这类词必须限定在医疗语境，否则会把
    # "a small treat for yourself"（正常表达）误判为违规 —— 实测踩过这个假阳性
    "违规承诺": (r"\b(fda[- ]approved"
                 r"|cures?\s+(acne|disease|pain|infection|condition|illness)"
                 r"|treats?\s+(acne|disease|pain|infection|condition|illness)"
                 r"|prevents?\s+(disease|infection|illness))\b"),
}


def check(title=None, highlights=None, bullets=None, search_terms=None):
    issues = []
    result = {}

    # ── 标题 ──
    if title:
        n = len(title)
        result["title"] = {"chars": n, "limit": LIMITS["title_chars"],
                           "ok": n <= LIMITS["title_chars"]}
        if n > LIMITS["title_chars"]:
            issues.append(f"标题超限：{n} 字符 > {LIMITS['title_chars']}")

    # ── 商品亮点 ──
    if highlights:
        n = len(highlights)
        result["item_highlights"] = {"chars": n, "limit": LIMITS["highlights_chars"],
                                     "ok": n <= LIMITS["highlights_chars"]}
        if n > LIMITS["highlights_chars"]:
            issues.append(f"商品亮点超限：{n} 字符 > {LIMITS['highlights_chars']}")

    # ── 五点 ──
    if bullets:
        bl = []
        total_bytes = 0
        for i, b in enumerate(bullets, 1):
            n = len(b)
            nb = len(b.encode("utf-8"))
            total_bytes += nb
            ok = LIMITS["bullet_min_chars"] <= n <= LIMITS["bullet_max_chars"]
            bl.append({"order": i, "chars": n, "bytes": nb, "ok": ok})
            if n > LIMITS["bullet_max_chars"]:
                issues.append(f"五点第 {i} 条超限：{n} 字符 > {LIMITS['bullet_max_chars']}")
            if n < LIMITS["bullet_min_chars"]:
                issues.append(f"五点第 {i} 条过短：{n} 字符 < {LIMITS['bullet_min_chars']}")
            if b.rstrip().endswith("."):
                issues.append(f"五点第 {i} 条以句号结尾（规范要求结尾不加标点）")
        result["bullets"] = {
            "count": len(bullets),
            "total_bytes": total_bytes,
            "bytes_ok": total_bytes <= LIMITS["bullet_total_bytes"],
            "items": bl,
        }
        if len(bullets) > 5:
            issues.append(f"五点超过 5 条：{len(bullets)}")
        if total_bytes > LIMITS["bullet_total_bytes"]:
            issues.append(f"五点总字节超限：{total_bytes} > {LIMITS['bullet_total_bytes']}（超出部分不被索引）")

    # ── Search Terms ──
    if search_terms:
        nb = len(search_terms.encode("utf-8"))
        result["search_terms"] = {"bytes": nb, "limit": LIMITS["search_terms_bytes"],
                                  "ok": nb <= LIMITS["search_terms_bytes"]}
        if nb > LIMITS["search_terms_bytes"]:
            issues.append(f"Search Terms 超限：{nb} bytes > {LIMITS['search_terms_bytes']}")

    # ── 禁用字符 ──
    all_text = " ".join(filter(None, [title, highlights, search_terms] + (bullets or [])))
    found_chars = sorted({c for c in FORBIDDEN_CHARS if c in all_text})
    result["forbidden_chars"] = found_chars
    if found_chars:
        issues.append(f"出现禁用字符：{' '.join(found_chars)}（{FORBIDDEN_CHARS_NOTE}）")

    # ── 同词重复（仅查标题，标题预算最紧）──
    if title:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-']*", title.lower())
        freq = {}
        for w in words:
            if w in STOPWORDS:
                continue
            freq[w] = freq.get(w, 0) + 1
        over = {w: c for w, c in freq.items() if c > 2}
        result["title_word_repeat"] = over
        if over:
            for w, c in over.items():
                issues.append(f"标题中「{w}」重复 {c} 次（规范：同词不超 2 次）")

    # ── 禁用话术 ──
    phrase_hits = {}
    for label, pat in FORBIDDEN_PHRASES.items():
        # 用 finditer + group(0)：正则含多个捕获组时 findall 会返回 tuple，
        # 后续 join 会报 TypeError（实测踩过）
        hits = sorted({x.group(0).strip() for x in re.finditer(pat, all_text, re.I)})
        if hits:
            phrase_hits[label] = hits
            issues.append(f"命中{label}话术：{', '.join(hits)}")
    result["forbidden_phrases"] = phrase_hits

    result["passed"] = not issues
    result["issues"] = issues
    result["checked_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="文案 json 文件路径")
    args = ap.parse_args()

    data = json.load(open(args.json, encoding="utf-8"))
    r = check(data.get("title"), data.get("item_highlights"),
              data.get("bullets"), data.get("search_terms"))

    print("=" * 72)
    print("Amazon Listing 合规自检")
    print("=" * 72)

    if "title" in r:
        t = r["title"]
        print(f"\n标题      {t['chars']:>4} / {t['limit']} 字符   {'✓' if t['ok'] else '✗ 超限'}")
    if "item_highlights" in r:
        h = r["item_highlights"]
        print(f"商品亮点  {h['chars']:>4} / {h['limit']} 字符   {'✓' if h['ok'] else '✗ 超限'}")
    if "bullets" in r:
        b = r["bullets"]
        print(f"\n五点共 {b['count']} 条，合计 {b['total_bytes']} bytes "
              f"/ {LIMITS['bullet_total_bytes']}   {'✓' if b['bytes_ok'] else '✗ 超限'}")
        for it in b["items"]:
            print(f"  第 {it['order']} 条  {it['chars']:>4} 字符  {it['bytes']:>4} bytes  "
                  f"{'✓' if it['ok'] else '✗'}")
    if "search_terms" in r:
        s = r["search_terms"]
        print(f"\nSearch Terms  {s['bytes']:>4} / {s['limit']} bytes   {'✓' if s['ok'] else '✗ 超限'}")

    print("\n" + "-" * 72)
    if r["forbidden_chars"]:
        print(f"禁用字符：{' '.join(r['forbidden_chars'])}")
    else:
        print("禁用字符：无 ✓")
    if r.get("title_word_repeat"):
        print(f"标题重复词：{r['title_word_repeat']}")
    else:
        print("标题重复词：无超过 2 次的词 ✓")
    if r["forbidden_phrases"]:
        print(f"禁用话术：{r['forbidden_phrases']}")
    else:
        print("禁用话术：未命中 ✓")

    print("\n" + "=" * 72)
    if r["passed"]:
        print("✅ 自检通过")
    else:
        print(f"❌ 自检未通过，{len(r['issues'])} 项待修：")
        for i, x in enumerate(r["issues"], 1):
            print(f"   {i}. {x}")
    print("=" * 72)

    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
