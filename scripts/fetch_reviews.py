#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
提取 Amazon listing 页内嵌的评论洞察数据（L2-a 路径，无需登录）

原理：Amazon 把 aspect 级评论分析以 `k+b64 <base64>` 形式注释在 HTML 的 k-injected 块里。
解码后取 AspectList 组件的 k-data.aspectsFlattened，得到若干维度，每个含：
  label / mentions / mentionsPercentage / sentiment / sentimentMentions / summary / snippets

用法：
  python fetch_reviews.py <ASIN> --project <代号> [--html <raw路径>]

默认 raw 路径：<项目>/02-竞品拆解/raw/<ASIN>.html（由 fetch_listing.py 产出）

⚠️ 结构依赖 Amazon 前端实现，改版即失效。脚本内置校验，解析失败会明确报错而不是给空数据。
"""
import base64
import html
import json
import os
import re
import sys
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
STAGE_DIR = "03-评论与VOC分析"

REQUIRED_ASPECT_FIELDS = ("label", "mentions", "sentiment", "sentimentMentions")


def die(msg):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def find_raw(project, asin):
    """按优先级找已存档的 raw HTML"""
    cands = [
        os.path.join(ROOT, project, "02-竞品拆解", "raw", f"{asin}.html"),
        os.path.join(ROOT, project, STAGE_DIR, "raw", f"{asin}.html"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def decode_blocks(page):
    """解出所有 k+b64 块"""
    out = []
    for b in re.findall(r"k\+b64\s+([A-Za-z0-9+/=]+)", page):
        try:
            raw = base64.b64decode(b + "=" * (-len(b) % 4))
            out.append(json.loads(raw.decode("utf-8", "ignore")))
        except Exception:
            continue
    return out


def extract_aspects(blocks):
    """从解码块里找 AspectList"""
    for d in blocks:
        if str(d.get("k-component", "")).startswith("AspectList"):
            asp = (d.get("k-data") or {}).get("aspectsFlattened")
            if asp:
                return asp, d.get("k-component")
    return None, None


def extract_summary(blocks):
    """AI 总摘要（SummaryFragments）"""
    for d in blocks:
        if str(d.get("k-component", "")).startswith("SummaryFragments"):
            frags = (d.get("k-data") or {}).get("fragments") or []
            texts = [html.unescape(f.get("inertText", "")) for f in frags if f.get("inertText")]
            if texts:
                return " ".join(texts).strip()
    return None


def flatten_snippet(s):
    """把 fragment 结构拼回纯文本，并取出被 Amazon 标为 strong 的关键短语"""
    if isinstance(s, str):
        return html.unescape(s), []
    parts, strongs = [], []
    txt = (s.get("text") or {}) if isinstance(s, dict) else {}
    for f in txt.get("fragments") or []:
        if "text" in f:
            parts.append(f["text"])
        sc = f.get("semanticContent") or {}
        inner = (sc.get("content") or {}).get("text")
        if inner:
            parts.append(inner)
            if sc.get("strong"):
                strongs.append(html.unescape(inner))
    url = ((s.get("review") or {}).get("url")) if isinstance(s, dict) else None
    return html.unescape("".join(parts)).strip(), strongs or ([url] if url else [])


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
    raw = opt("--html", None) or find_raw(project, asin)
    if not raw or not os.path.isfile(raw):
        die(f"找不到 raw HTML。请先运行 fetch_listing.py，或用 --html 指定路径。")
    print(f"读取 raw：{raw}")

    page = open(raw, encoding="utf-8").read()
    blocks = decode_blocks(page)
    print(f"解码 k+b64 块：{len(blocks)}")

    aspects_raw, comp = extract_aspects(blocks)
    if not aspects_raw:
        die("未找到 AspectList.aspectsFlattened —— Amazon 可能已改版。"
            "请降级到 L3 并标注，不要用旧数据填充。")
    print(f"命中组件：{comp}，维度数：{len(aspects_raw)}")

    aspects = []
    for a in aspects_raw:
        missing = [f for f in REQUIRED_ASPECT_FIELDS if a.get(f) is None]
        m = a.get("mentions") or 0
        sm = a.get("sentimentMentions") or 0
        ev, strongs = [], []
        for s in a.get("snippets") or []:
            t, st = flatten_snippet(s)
            if t:
                ev.append(t)
            strongs.extend(st)
        aspects.append({
            "label": a.get("label"),
            "mentions": m,
            "mentions_pct": a.get("mentionsPercentage"),
            "sentiment": a.get("sentiment"),
            "sentiment_mentions": sm,
            "non_positive_mentions": (m - sm) if m else None,
            "positive_rate": round(sm / m, 3) if m else None,
            "summary": html.unescape(a.get("summary") or ""),
            "evidence_snippets": ev,
            "strong_phrases": strongs,
            "field_check": "OK" if not missing else f"缺字段: {missing}",
        })

    aspects.sort(key=lambda x: -(x["mentions"] or 0))

    data = {
        "asin": asin,
        "extracted_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "data_path": "L2-a",
        "origin": "listing 页内嵌 AspectList（k+b64 解码）",
        "source_grade": "S4",
        "note": "维度名与摘要为 Amazon 官方生成；snippets 为 Amazon 精选片段，存在选择性偏差",
        "component": comp,
        "overall_summary": extract_summary(blocks),
        "aspect_count": len(aspects),
        "aspects": aspects,
    }

    outdir = os.path.join(ROOT, project, STAGE_DIR, "raw")
    os.makedirs(outdir, exist_ok=True)
    # 归档原始提取结果，供复核
    with open(os.path.join(outdir, f"{asin}_aspects.raw.json"), "w", encoding="utf-8") as f:
        json.dump(aspects_raw, f, ensure_ascii=False, indent=2)
    # 规范化的分析输入
    out = os.path.join(outdir, f"{asin}_aspects.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n原始提取 → {os.path.join(outdir, asin + '_aspects.raw.json')}")
    print(f"规范化   → {out}")
    print()
    if data["overall_summary"]:
        print("【AI 总摘要】")
        print(" ", data["overall_summary"][:500])
        print()
    print(f"{'维度':<18}{'提及':>5}{'占比':>7}{'正面':>5}{'正面率':>8}  情感")
    print("-" * 60)
    for a in aspects:
        pr = a["positive_rate"]
        flag = "" if pr is None or pr >= 0.99 else ("  ← 风险" if pr < 0.85 else "  ← 注意")
        print(f"{a['label']:<18}{a['mentions']:>5}{str(a['mentions_pct']) + '%':>7}"
              f"{a['sentiment_mentions']:>5}{(str(round(pr*100,1)) + '%') if pr is not None else '-':>8}"
              f"  {a['sentiment']}{flag}")


if __name__ == "__main__":
    main()
