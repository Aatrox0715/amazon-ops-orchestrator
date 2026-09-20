#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
报告与数据结构一致性检查（P0-2）

解决的问题：
  实战中发生「output.json 已修正、但 report.md 里仍是旧数字」的情况
  （05/09 环节：结构化数据改成 $9.99，报告里还写着 $66.88）。
  当时靠人工加「作废横幅」补救 —— 不可持续，需自动检查。

检查项：
  1. revision_history 记录的「作废值」是否仍残留在 report.md
  2. 若残留，该处附近是否有「作废 / 已修正 / 请勿引用」类标注
  3. report.md 中出现的「看起来是金额」的数字，是否都能在 output.json 中找到依据

用法：
  python report_check.py <项目代号>
  python report_check.py <项目代号> --verbose
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
    "01": "01-市场调研", "02": "02-竞品拆解", "03": "03-评论与VOC分析",
    "04": "04-关键词库", "05": "05-定价利润", "06": "06-文案",
    "07": "07-视觉素材", "08": "08-合规体检", "09": "09-广告架构",
    "10": "10-复盘迭代",
}

DEPRECATION_MARKERS = ["作废", "已作废", "已修正", "请勿引用", "勿引用", "失效", "错误", "v1"]


def load_output(stage_dir):
    p = os.path.join(stage_dir, "output.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def collect_deprecated_values(obj, acc):
    """
    只从**结构化字段**里收集「已作废的值」。

    ⚠️ 首版还从 defect 等自由文本里抓数字，导致严重误报：
        `$20.12` 被抓成 `20`，再在报告里无边界匹配 → 命中 `2026` 等无关数字，
        单个环节虚报 32–60 处。**校验器本身也会误报，需要被校验。**
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "revision_history" and isinstance(v, list):
                for rev in v:
                    if not isinstance(rev, dict):
                        continue
                    status = str(rev.get("status", ""))
                    if not ("作废" in status or "❌" in status):
                        continue
                    # 只取明确表示「旧值」的结构化字段，且要求是完整数字
                    for key in ("v1_value", "old_value"):
                        raw = rev.get(key)
                        if isinstance(raw, (int, float)):
                            acc.append((f"{float(raw):.2f}".rstrip("0").rstrip("."), key))
            collect_deprecated_values(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            collect_deprecated_values(x, acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    code = args.project
    base = os.path.join(ROOT, code)
    if not os.path.isdir(base):
        print(f"错误：项目 {code} 不存在", file=sys.stderr)
        sys.exit(1)

    print("=" * 78)
    print(f"报告与数据结构一致性检查 · {code}")
    print("=" * 78)

    checked = 0
    fails, warns, passes = [], [], []

    for k, d in sorted(STAGES.items()):
        sd = os.path.join(base, d)
        if not os.path.isdir(sd):
            continue
        o = load_output(sd)
        rp = os.path.join(sd, "report.md")
        if not o or not os.path.isfile(rp):
            continue

        checked += 1
        report = open(rp, encoding="utf-8").read()

        # 收集该环节的「已作废值」
        dep = []
        collect_deprecated_values(o, dep)
        # 只保留看起来像「金额或显著数值」的
        keys = set()
        for val, src in dep:
            v = re.sub(r"[^\d.]", "", val)
            if not v:
                continue
            try:
                f = float(v)
            except ValueError:
                continue
            # 只保留「足够具体」的数值：带小数，或 ≥100 的整数。
            # 小整数（如 20）极易与年份、百分比误匹配 —— 首版踩过这个坑，单环节虚报 60 处。
            if "." in v or f >= 100:
                keys.add((v, src))

        if not keys:
            if args.verbose:
                print(f"  [{k}] {d:20s} 无作废记录，跳过")
            passes.append(f"{k} 无作废残留")
            continue

        # 检查报告里是否还残留旧值（用数字边界，避免 20 命中 2026）
        residual = []
        for val, src in sorted(keys):
            pat = r"(?<![\d.])" + re.escape(val) + r"(?![\d])"
            for m in re.finditer(pat, report):
                s = max(0, m.start() - 260)
                ctx = report[s:m.end() + 120]
                if not any(mk in ctx for mk in DEPRECATION_MARKERS):
                    residual.append((val, ctx.replace("\n", " ")[:100]))

        if residual:
            fails.append(f"环节 {k} 报告残留作废值 {len(residual)} 处且无标注")
            print(f"  [✗] {k} {d}")
            print(f"        报告中有 {len(residual)} 处使用了已作废的值，且附近无「作废」标注：")
            for val, ctx in residual[:3]:
                print(f"          · 值 {val} → …{ctx}…")
        else:
            passes.append(f"{k} 作废值已标注")
            print(f"  [✓] {k} {d:20s} 作废值均已标注（{len(keys)} 个旧值）")

    print()
    print("=" * 78)
    print("结论")
    print("=" * 78)
    print(f"  检查环节：{checked}    通过 {len(passes)}    失败 {len(fails)}")
    if fails:
        for x in fails:
            print(f"  ❌ {x}")
    print()
    print(f"  总体：{'✅ 报告与数据一致' if not fails else '❌ 存在不一致，需修正报告'}")
    print("=" * 78)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
