#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
外部依赖时效检查（P1-6）

背景：本技能的费率口径依赖 `amazon-coach` 的闪卡。那些卡自带
`verifiedAt` / `volatile` / `reviewDueAt` 三字段，其中：
  volatile = true（含金额/费率/政策日期）→ 6 个月复核一次
  volatile = false（规则稳定的知识）→ 18 个月复核一次

风险：费率卡到期后若不主动复核，会**静默使用过期费率** ——
这与「币种读错」同性质：看不出来，但结论会错。

用法：
  python dep_check.py [--coach-dir <amazon-coach 路径>] [--warn-days 30]

退出码：0 = 无到期项；1 = 有已过期项
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── 统一配置（三级回退，替代硬编码路径）──
try:
    from _config import project_root, coach_dir, coach_mode, SKILL_ROOT
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from _config import project_root, coach_dir, coach_mode, SKILL_ROOT


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_COACH = coach_dir()
TZ = timezone(timedelta(hours=8))

# 本技能实际依赖的卡片（费率 / 规范 / 定义类）
REQUIRED_CARDS = {
    "f001": "标题 75 字符 + 商品亮点 125 字符规范",
    "f003": "五点 10–255 字符规范",
    "f009": "FBA 尺寸分段（2026 版）",
    "f011": "ACoS / TACoS 定义与阶段目标",
    "f020": "Vine 费用分档",
    "f029": "IPI 库存绩效",
    "f039": "新手选品三大坑（含低货值警示）",
    "f087": "标题字符硬上限",
    "f088": "商品亮点 vs 五点上限",
    "f089": "2026-07 标题新规要点",
    "f095": "FBA 尺寸分段临界点",
    "f096": "FBA 仓储费 + 超龄附加费",
    "f098": "FBA 贴标 2026 变化",
    "f108": "毛利率目标线（25–30% 能干）",
    "f120": "超龄库存附加费 8 档",
    "f132": "低库存水平费",
    "f133": "入库配置服务费",
    "f136": "2026 FBA 配送费 + 低价减免",
    "f138": "旺季促销节点 + 旺季配送费",
    "f141": "大促价格双回溯规则",
}


def parse_ym(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m").replace(tzinfo=TZ)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coach-dir", default=DEFAULT_COACH)
    ap.add_argument("--warn-days", type=int, default=30)
    args = ap.parse_args()

    mode, mode_path, mode_msg = coach_mode(args.coach_dir)

    print("=" * 78)
    print("外部依赖时效检查")
    print("=" * 78)
    print(f"依赖源  ：{args.coach_dir}")
    print(f"模式    ：{mode} —— {mode_msg}")
    if mode == "内置":
        print("          （未配置外部 amazon-coach，使用技能自带卡片集；")
        print("            时效字段来自打包时的快照，不反映上游最新复核状态）")

    # 外部用 flashcards.json；离线兜底用 min-cards.json
    fp = None
    for name in ("flashcards.json", "min-cards.json"):
        cand = os.path.join(args.coach_dir, name)
        if os.path.isfile(cand):
            fp = cand
            break

    if not fp:
        print(f"\n❌ 依赖源内既无 flashcards.json 也无 min-cards.json")
        print("   → 请指定正确路径：--coach-dir <amazon-coach/data>")
        print("   → 或检查技能自带的 data/ 是否被删除")
        return 1

    print(f"卡片文件：{os.path.basename(fp)}")
    print()

    payload = json.load(open(fp, encoding="utf-8"))
    cards = payload["cards"] if isinstance(payload, dict) else payload
    idx = {c["id"]: c for c in cards}
    now = datetime.now(TZ)

    print(f"卡片总数：{len(cards)}    本技能引用：{len(REQUIRED_CARDS)} 张")
    print()

    expired, soon, ok, missing = [], [], [], []
    for cid, desc in sorted(REQUIRED_CARDS.items()):
        c = idx.get(cid)
        if not c:
            missing.append((cid, desc))
            continue
        due = c.get("reviewDueAt")
        verified = c.get("verifiedAt")
        volatile = c.get("volatile")
        d = None
        try:
            d = datetime.strptime(due, "%Y-%m-%d").replace(tzinfo=TZ) if due else None
        except Exception:
            pass

        if not d:
            ok.append((cid, desc, due, verified))
            continue
        delta = (d - now).days
        if delta < 0:
            expired.append((cid, desc, due, verified, volatile, delta))
        elif delta <= args.warn_days:
            soon.append((cid, desc, due, verified, volatile, delta))
        else:
            ok.append((cid, desc, due, verified))

    if expired:
        print("🔴 已过期（引用前必须联网核实官方口径）")
        for cid, desc, due, va, vol, delta in expired:
            print(f"   {cid}  {desc}")
            print(f"        过期 {-delta} 天（{due}，核实于 {va}，volatile={vol}）")
        print()

    if soon:
        print("🟡 临近到期（建议提前复核）")
        for cid, desc, due, va, vol, delta in soon:
            print(f"   {cid}  {desc}  —— 还有 {delta} 天（{due}）")
        print()

    if missing:
        print("⚠️ 缺失（本技能引用了但依赖源里没有）")
        for cid, desc in missing:
            print(f"   {cid}  {desc}")
        print()

    print("✅ 有效期内")
    for cid, desc, due, va in ok:
        print(f"   {cid}  {desc}  （{due}）")

    print()
    print("=" * 78)
    print(f"结论：过期 {len(expired)} / 临近 {len(soon)} / 有效 {len(ok)} / 缺失 {len(missing)}")
    if expired:
        print("   ❌ 存在过期依赖，引用前必须联网核实")
    elif soon or missing:
        print("   ⚠️  建议尽快复核临近到期项")
    else:
        print("   ✅ 全部依赖在有效期内")
    print("=" * 78)
    return 1 if expired else 0


if __name__ == "__main__":
    sys.exit(main())
