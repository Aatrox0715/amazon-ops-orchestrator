#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数值语义校验（P0-1）+ 假设追踪（P0-3）

为什么要独立成一个脚本：
  crosscheck.py 已能通过 21 项检查，但它的「基数级校验」只覆盖了币种这一个特例。
  本次把它通用化 —— 覆盖金额/度量/比率/计数四类，并对「假设字段」做追踪。
  独立成脚本是为了不破坏已验证的 crosscheck 逻辑，两者互补。

规范依据：references/06-numeric-semantics.md

用法：
  python semantic_check.py <项目代号> [--verbose]
"""
import argparse
import json
import os
import re
import sys

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
STAGES = {
    "02": "02-竞品拆解", "03": "03-评论与VOC分析", "04": "04-关键词库",
    "05": "05-定价利润", "06": "06-文案", "07": "07-视觉素材",
    "08": "08-合规体检", "09": "09-广告架构", "10": "10-复盘迭代",
}

# 只对「真正会因单位/币种不明而出错」的两类强制要求元数据：
#   金额 —— 币种差异（已实际出错：CNY 被当 USD）
#   度量 —— 单位差异（英寸/厘米、克/盎司、立方英尺）
# 比率与计数不强制：带 _pct / rate 后缀者语义自明，纯计数本身无歧义。
#
# ⚠️ 首版把比率/计数也纳入强制，结果产生 63 项误报（连「标题字符数」都被要求写单位）。
# 误报泛滥会让校验被忽略、失去价值 —— 校验器本身也需要被校验。
PATTERNS = [
    ("金额", re.compile(r"^(sell_)?price$|^price_usd$|_price$|"
                        r"^cost$|_cost$|^cost_|_fee$|^fee$|_amount$|^amount$|"
                        r"^revenue$|^profit$|^sales$|^budget$|_bid$|^bid$|"
                        r"_ceiling$|^ceiling$", re.I), "currency"),
    ("度量", re.compile(r"^weight|_weight$|dimension|^length$|^width$|^height$|"
                        r"_volume$|^volume$|cbm|_inches$|_cm$|_grams$|_lb$|_oz$", re.I), "unit"),
]

# 已知为「结构/标识」而非待校验数值的字段（白名单）
SKIP_KEYS = {
    "stage", "project", "asin", "slot", "order", "priority", "index",
    "version", "page", "rank", "bsr_rank", "slot_id", "confidence",
}

# 免费词汇的数字上限（超过则视为可疑的"未标元数据的数值"）
BIG_NUMBER = 3.0

META_BY_NEED = {
    "currency": ["currency"],
    "unit": ["unit"],
    "scale": ["scale", "unit"],
}


def walk(obj, path, acc, parent=None):
    """递归收集 (路径, 键名, 值, 父对象)
    带父对象是为了能在「字段同样的层级」找元数据 ——
    例如 currency 常与 price 并置在同一个对象里，而非顶层 payload。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                acc.append((p, k, v, obj))
            else:
                walk(v, p, acc, obj)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            walk(x, f"{path}[{i}]", acc, parent)


def find_meta(payload, key, need):
    """在 payload 同一层或其父层找元数据"""
    for cand in META_BY_NEED.get(need, []):
        if cand in payload:
            v = payload[cand]
            if isinstance(v, str) and v:
                return v
    # 名字相关字段：如 price_currency / unit
    for cand in list(payload.keys()):
        if key.split("_")[0] in cand and any(m in cand for m in META_BY_NEED.get(need, [])):
            v = payload[cand]
            if isinstance(v, str) and v:
                return v
    return None


def find_assumptions(obj, path, acc):
    """找出被标为假设的字段"""
    if isinstance(obj, dict):
        if obj.get("is_assumption") is True:
            acc.append({
                "path": path,
                "basis": obj.get("assumption_basis") or obj.get("basis"),
                "impact": obj.get("impact"),
                "verify": obj.get("how_to_verify"),
            })
        for k, v in obj.items():
            find_assumptions(v, f"{path}.{k}" if path else k, acc)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            find_assumptions(x, f"{path}[{i}]", acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    base = os.path.join(ROOT, args.project)
    if not os.path.isdir(base):
        print(f"错误：项目 {args.project} 不存在", file=sys.stderr)
        sys.exit(1)

    print("=" * 78)
    print(f"数值语义校验 + 假设追踪 · {args.project}")
    print("=" * 78)
    print(f"规范依据：references/06-numeric-semantics.md")
    print()

    fails, warns, passes = [], [], []
    all_currencies = {}

    # ── 1. 数值字段分类与元数据齐备性 ──
    print("─" * 78)
    print("1. 数值字段元数据齐备性")
    print("─" * 78)

    unclassified_total = 0
    for k, d in sorted(STAGES.items()):
        p = os.path.join(base, d, "output.json")
        if not os.path.isfile(p):
            continue
        try:
            o = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        payload = o.get("payload") or {}

        nums = []
        walk(payload, "", nums)

        missing = []
        unclassified = []
        for path, key, val, parent in nums:
            if key in SKIP_KEYS or "bsr" in key.lower():
                continue
            label, need = None, None
            for lab, pat, nd in PATTERNS:
                if pat.search(key):
                    label, need = lab, nd
                    break
            if not label:
                if abs(val) >= BIG_NUMBER and val not in (0.0, 1.0, 2.0):
                    unclassified.append((path, key, val))
                continue
            # 元数据在「同层级」找（price 与 currency 常并置）
            meta = find_meta(parent if isinstance(parent, dict) else payload, key, need)
            if not meta and parent is not payload:
                meta = find_meta(payload, key, need)
            if not meta:
                missing.append((path, key, val, label, need))
            elif need == "currency":
                all_currencies.setdefault(k, set()).add(meta)

        if missing:
            fails.append(f"{k} 有 {len(missing)} 个数值字段缺元数据")
            print(f"  [✗] {k} {d}")
            for path, key, val, label, need in missing[:5]:
                print(f"        · {path} = {val}（{label}）缺 {need}")
        else:
            passes.append(f"{k} 元数据齐备")
            print(f"  [✓] {k} {d:20s} 数值字段元数据齐备")

        unclassified_total += len(unclassified)
        if unclassified and args.verbose:
            print(f"        （未归类字段 {len(unclassified)} 个，需人工确认）")
            for path, key, val in unclassified[:4]:
                print(f"          ? {path} = {val}")

    if unclassified_total:
        warns.append(f"共 {unclassified_total} 个数值字段无法自动归类")
        print(f"\n  [⚠] 有 {unclassified_total} 个数值字段未匹配到类型模式（建议补进规范的模式表）")

    # ── 2. 币种跨环节一致性 ──
    print()
    print("─" * 78)
    print("2. 币种跨环节一致性")
    print("─" * 78)
    flat = {}
    for k, s in all_currencies.items():
        flat[k] = sorted(s)
        print(f"  {k}: {flat[k]}")
    allv = {v for s in all_currencies.values() for v in s}
    if len(allv) <= 1:
        passes.append("币种一致")
        print(f"  [✓] 全项目币种一致：{allv.pop() if allv else '未检出'}")
    else:
        fails.append(f"币种不一致：{flat}")
        print(f"  [✗] 币种不一致：{flat}")

    # ── 3. 假设字段追踪 ──
    print()
    print("─" * 78)
    print("3. 假设字段追踪")
    print("─" * 78)
    total_assump = 0
    incomplete = []
    for k, d in sorted(STAGES.items()):
        p = os.path.join(base, d, "output.json")
        if not os.path.isfile(p):
            continue
        try:
            o = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        acc = []
        find_assumptions(o.get("payload") or {}, "", acc)
        # 兼容：文本型假设（含「假设」「assumption」的字段）
        txt = json.dumps(o.get("payload") or {}, ensure_ascii=False)
        has_assumption_note = ("is_assumption" in txt or "假设" in txt)
        if acc:
            total_assump += len(acc)
            bad = [a for a in acc if not a.get("basis") or not a.get("verify")]
            if bad:
                incomplete.extend([f"{k}:{a['path']}" for a in bad])
                print(f"  [⚠] {k} {d:20s} {len(acc)} 个假设，其中 {len(bad)} 个缺 basis/verify")
            else:
                passes.append(f"{k} 假设标注完整")
                print(f"  [✓] {k} {d:20s} {len(acc)} 个假设均含 basis + impact + verify")
        elif has_assumption_note:
            passes.append(f"{k} 有文本型假设标注")
            print(f"  [i] {k} {d:20s} 含假设说明（文本型，未结构化）")

    if total_assump == 0:
        warns.append("全项目未检出结构化假设字段（is_assumption）")
        print("  [⚠] 未检出 is_assumption 结构化标注 —— 建议按规范补上，否则假设会被当事实引用")
    if incomplete:
        fails.append(f"{len(incomplete)} 个假设缺验证方式")
        for x in incomplete[:5]:
            print(f"        · {x}")

    # ── 结论 ──
    print()
    print("=" * 78)
    print("结论")
    print("=" * 78)
    print(f"  ✅ 通过 {len(passes)} 项")
    if warns:
        print(f"  ⚠️  提示 {len(warns)} 项")
        for w in warns:
            print(f"     · {w}")
    if fails:
        print(f"  ❌ 失败 {len(fails)} 项")
        for x in fails:
            print(f"     · {x}")
    print()
    print(f"  总体：{'✅ 数值语义与假设标注合规' if not fails else '❌ 存在不合规项'}")
    print("=" * 78)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
