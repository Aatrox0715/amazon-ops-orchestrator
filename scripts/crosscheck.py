#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨环节交叉一致性检查

selfcheck.py 只验「文件在不在」，本脚本验「内容对不对」——
检查同一事实在不同环节是否被一致引用，以及内部数字是否自洽。

用法：
  python crosscheck.py <项目代号>

检查类型：
  1. 关键数字跨环节一致性（售价、平台费、成本上限、佣金率…）
  2. 环节间引用链完整性（VOC → 五点排序 → 图位）
  3. 内部数字自洽（如盈亏平衡 ACoS 与公式复算）
  4. 定稿状态一致性（P1 环节是否 finalized）
"""
import argparse
import json
import os
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


def load(project, sub):
    p = os.path.join(ROOT, project, sub, "output.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


class R:
    def __init__(self):
        self.rows = []

    def add(self, name, a_src, a_val, b_src, b_val, ok, note=""):
        self.rows.append((name, a_src, a_val, b_src, b_val, ok, note))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    args = ap.parse_args()
    code = args.project

    o02 = load(code, "02-竞品拆解")
    o03 = load(code, "03-评论与VOC分析")
    o04 = load(code, "04-关键词库")
    o05 = load(code, "05-定价利润")
    o06 = load(code, "06-文案")
    o07 = load(code, "07-视觉素材")
    o08 = load(code, "08-合规体检")
    o09 = load(code, "09-广告架构")
    o10 = load(code, "10-复盘迭代")

    print("=" * 78)
    print(f"跨环节一致性检查 · {code}")
    print(f"时间：{datetime.now(TZ).isoformat(timespec='seconds')}")
    print("=" * 78)

    fails, warns, passes = [], [], []

    def chk(name, a_src, a_val, b_src, b_val, tol=1e-6, note=""):
        ok = (a_val == b_val) if isinstance(a_val, str) else (
            a_val is not None and b_val is not None and abs(float(a_val) - float(b_val)) <= tol)
        tag = "✓" if ok else "✗"
        print(f"  [{tag}] {name}")
        print(f"        {a_src}: {a_val}")
        if not ok:
            print(f"        {b_src}: {b_val}   ← 不一致")
        (passes if ok else fails).append(name)
        return ok

    def info(name, val, src):
        print(f"  [i] {name}: {val}   ({src})")

    # ── 0. 基数级校验（币种 / 单位）★ 新增 ──
    print()
    print("─" * 78)
    print("0. 基数级校验（币种 / 单位）★")
    print("─" * 78)
    print("  背景：一致性检查发现不了『共同的错误前提』。")
    print("        曾发生售价币种读错（CNY 当 USD）而 21 项交叉检查全过的案例。")
    print("        故币种/单位类校验必须单独设关卡。")
    print()

    currencies = {}
    if o02:
        currencies["02"] = o02["payload"]["target_asins"][0].get("currency")
    if o05:
        currencies["05"] = o05["payload"].get("currency")
    if o09:
        currencies["09"] = o09["payload"].get("currency")

    missing_cur = [k for k, v in currencies.items() if not v]
    if missing_cur:
        fails.append(f"环节 {','.join(missing_cur)} 数值字段未标注币种")
        print(f"  [✗] 未标注币种的环节：{missing_cur} → 基数级校验无法进行")
        print("      → 应在 output.json 的价格字段旁显式写 currency")
    else:
        uniq = set(currencies.values())
        if len(uniq) == 1:
            passes.append("币种一致")
            print(f"  [✓] 各环节币种一致：{uniq.pop()}"
                  f"（来自环节 {', '.join(sorted(currencies))}）")
        else:
            fails.append(f"币种不一致：{currencies}")
            print(f"  [✗] 币种不一致：{currencies}")

    # 价格数值一致性
    if o02 and o05:
        t0 = o02["payload"]["target_asins"][0]
        p02 = t0.get("price", t0.get("price_usd"))
        p05 = o05["payload"]["sell_price"]
        chk("售价（环节02 实测 ↔ 环节05 测算基准）", "02", p02, "05", p05, tol=0.01)

    # 平台费跨环节校验（不硬编码数值 —— 曾因硬编码旧价导致 KeyError，教训）
    if o05 and o09:
        p05 = o05["payload"]
        rng = p05.get("platform_fee_range") or {}
        f05_min, f05_max = rng.get("min"), rng.get("max")
        if f05_min is None and "total_platform_fee" in p05:
            f05_min = f05_max = p05["total_platform_fee"]

        be2 = (o09["payload"].get("break_even_acos_v2") or {}).get("scenarios") or []
        f09_set = sorted({s["platform_fee"] for s in be2
                          if s.get("platform_fee") is not None})

        if f05_min is not None:
            print(f"        05 平台费区间: ${f05_min} – ${f05_max}")
        if f09_set:
            print(f"        09 引用平台费: {f09_set}")

        if f09_set and f05_min is not None:
            lo, hi = round(f05_min - 0.01, 2), round(f05_max + 0.01, 2)
            in_range = all(lo <= v <= hi for v in f09_set)
            tag = "✓" if in_range else "✗"
            print(f"  [{tag}] 平台费（环节05 区间 ↔ 环节09 引用）")
            (passes if in_range else fails).append("平台费引用一致")
        else:
            warns.append("平台费跨环节校验未执行（字段缺失）")
            print("  [⚠] 平台费跨环节校验未执行（字段缺失）")

    if o05:
        rate = o05["payload"]["category"]["referral_rate"]
        info("佣金率", f"{rate*100:.0f}%（珠宝类目）", "05")
        if abs(rate - 0.20) < 1e-9:
            passes.append("佣金率 20%")
        else:
            fails.append("佣金率非 20%")

    # ── 2. 内部数字自洽 ──
    print()
    print("─" * 78)
    print("2. 内部数字自洽（复算验证）")
    print("─" * 78)

    # 盈亏平衡 ACoS 复算（适配 v2 的 scenarios 结构）
    if o05 and o09:
        p = o05["payload"]["sell_price"]
        scenarios = (o09["payload"].get("break_even_acos_v2") or {}).get("scenarios") or []
        all_ok = True
        for s in scenarios:
            plat = s.get("platform_fee")
            cp = s.get("purchase_plus_freight")
            stated = s.get("break_even_acos")
            if None in (plat, cp, stated):
                continue
            recomputed = round((p - plat - cp) / p, 4)
            if abs(recomputed - stated) > 0.002:
                all_ok = False
                print(f"  [✗] 盈亏平衡 ACoS 复算不符：声明 {stated} vs 复算 {recomputed}"
                      f"（平台费 ${plat} / 采购+头程 ${cp}）")
        if scenarios:
            tag = "✓" if all_ok else "✗"
            print(f"  [{tag}] 盈亏平衡 ACoS 复算（{len(scenarios)} 个情景，用环节05 售价复算）")
            (passes if all_ok else fails).append("盈亏平衡 ACoS 复算")
        else:
            warns.append("盈亏平衡 ACoS 未复算（缺 scenarios）")
            print("  [⚠] 盈亏平衡 ACoS 未复算（缺 scenarios）")

    # 五点字符数复算
    if o06:
        b = o06["payload"]["bullets"]
        bad = [x for x in b if len(x["text"]) != x["char_count"]]
        if bad:
            fails.append("五点字符数声明与实际不符")
            print(f"  [✗] 五点字符数声明与实际不符：{len(bad)} 条")
        else:
            passes.append("五点字符数")
            print(f"  [✓] 五点字符数声明与实际一致（{len(b)} 条）")

        t = o06["payload"]["title_options"][0]
        if len(t["text"]) != t["char_count"]:
            fails.append("标题字符数与声明不符")
            print(f"  [✗] 标题字符数声明 {t['char_count']} ≠ 实际 {len(t['text'])}")
        else:
            passes.append("标题字符数")
            print(f"  [✓] 标题字符数声明与实际一致（{t['char_count']} 字符）")

    # ── 3. 引用链完整性 ──
    print()
    print("─" * 78)
    print("3. 环节间引用链（VOC → 五点 → 图位）")
    print("─" * 78)

    if o06:
        bl = o06["payload"]["bullets"]
        with_basis = [x for x in bl if x.get("voc_basis")]
        print(f"  [{'✓' if len(with_basis) == len(bl) else '✗'}] "
              f"五点均标注 VOC 依据：{len(with_basis)}/{len(bl)}")
        (passes if len(with_basis) == len(bl) else fails).append("五点 VOC 依据")

        # 五点第1条应为 versatility
        first_is_vers = "VERSATILE" in bl[0]["head"].upper()
        print(f"  [{'✓' if first_is_vers else '✗'}] 五点第1条为 VERSATILE（VOC 最强维度）")
        (passes if first_is_vers else fails).append("五点排序依据")

        # delicacy 不应独立成条
        has_delicacy = any("DAINTY" in x["head"].upper() or "DELICATE" in x["head"].upper()
                           for x in bl)
        print(f"  [{'✓' if not has_delicacy else '✗'}] delicacy 未独立成条（风险维度不当主推）")
        (passes if not has_delicacy else warns).append("delicacy 处理")

    if o07 and o06:
        slots = o07["payload"]["image_slots"]
        linked = [s for s in slots if s.get("bullet_link", "").startswith("五点")]
        print(f"  [{'✓' if len(linked) >= 5 else '⚠'}] 图位与五点建立对应：{len(linked)} 个图位关联五点")
        (passes if len(linked) >= 5 else warns).append("图文对应")

        # 检查图2是否对应五点1
        s2 = [s for s in slots if s["slot"] == 2]
        if s2:
            ok = "五点第 1 条" in (s2[0].get("bullet_link") or "")
            print(f"  [{'✓' if ok else '✗'}] 图2 对应五点第1条（图文严格一致）")
            (passes if ok else fails).append("图2对应五点1")

    # ── 4. 观察定性闭环 ──
    print()
    print("─" * 78)
    print("4. 环节02 未定性观察是否被环节08 闭环")
    print("─" * 78)

    if o02 and o08:
        # 环节02 有没有标注 observation
        src = json.dumps(o02, ensure_ascii=False)
        has_obs = "观察" in src and ("why_not_conclusive" in src or "status" in src)
        print(f"  [{'✓' if has_obs else '⚠'}] 环节02 存在『观察（未定性）』标注")
        (passes if has_obs else warns).append("02 观察标注")

        resolved = o08["payload"].get("observations_resolved") or []
        print(f"  [{'✓' if len(resolved) >= 2 else '⚠'}] 环节08 处理的观察条数：{len(resolved)}")
        (passes if len(resolved) >= 2 else warns).append("08 观察闭环")

        still = [x for x in resolved if x.get("status") != "resolved"]
        print(f"  [i] 其中仍为未定状态：{len(still)} 条")

    # ── 5. 定稿状态一致性 ──
    print()
    print("─" * 78)
    print("5. P1 环节定稿状态")
    print("─" * 78)

    p1_map = {"04": ("关键词库搭建", o04), "05": ("定价与利润测算", o05),
              "06": ("Listing文案编写", o06), "07": ("视觉素材规划", o07),
              "08": ("合规与质量体检", o08), "09": ("广告架构规划", o09)}
    for k, (name, o) in p1_map.items():
        if not o:
            print(f"  [⚠] {k} {name}: output.json 缺失")
            warns.append(f"{k} 缺失")
            continue
        pay = o.get("payload", {})
        final = pay.get("finalized") or any(
            pay.get(x) is not None for x in
            ("selected_strategy", "selected_option", "selected_title_option"))
        conf = o.get("confirmed_by_user") or []
        tag = "✓" if final else "✗"
        print(f"  [{tag}] {k} {name:<16} finalized={bool(final)}  决策留痕={len(conf)} 条")
        (passes if final else fails).append(f"{k} 定稿")

    # 环节10 特殊：iteration_targets 应为空
    if o10:
        it = o10["payload"].get("iteration_targets")
        has_data = o10["payload"]["data_availability"]["has_real_data"]
        if not has_data and it == []:
            passes.append("10 无数据时 iteration_targets 为空")
            print(f"  [✓] 10 无实际数据 → iteration_targets 保持为空（未编造结论）")
        elif not has_data and it:
            fails.append("10 无数据却填了 iteration_targets")
            print(f"  [✗] 10 无实际数据却填了 {len(it)} 条迭代目标 ← 疑似编造")
        else:
            print(f"  [i] 10 有实际数据，iteration_targets 应有内容")

    # ── 结论 ──
    print()
    print("=" * 78)
    print("交叉检查结论")
    print("=" * 78)
    print(f"  ✅ 通过 {len(passes)} 项")
    if warns:
        print(f"  ⚠️  提示 {len(warns)} 项：{'、'.join(warns)}")
    if fails:
        print(f"  ❌ 不一致 {len(fails)} 项：{'、'.join(fails)}")
    print()
    print(f"  总体：{'✅ 全套一致' if not fails else '❌ 存在不一致项'}")
    print("=" * 78)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
