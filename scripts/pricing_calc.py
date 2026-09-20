#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
亚马逊单品利润与成本上限测算器

设计原则：
  1. **采购价未知时反推成本上限**，不给「这个价能赚 $X」这种假单点结论
  2. 支持跨尺寸分段的敏感性分析（包装多 1 公分值多少钱）
  3. 费率锚点标注来源，缺口明确标出，不插值造假

用法：
  python pricing_calc.py --price 66.88 --category-rate 0.20 --size-tier large_standard
  python pricing_calc.py --price 66.88 --category-rate 0.20 --size-tier both --json out.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TZ = timezone(timedelta(hours=8))

# ── 2026 官方费率锚点（S1：Amazon Seller Central 费率表，经 amazon-coach 闪卡核实）──
FBA_FULFILLMENT_2026 = {
    "small_standard": {
        "desc": "≤16 oz (453 g)，最长边 ≤15 in，中边 ≤12 in，短边 ≤0.75 in (1.9 cm)",
        "anchors": {"≤2 oz": 3.06, "12–16 oz": 3.63},
        "note": "2026-01 起标准件平均上调 $0.04–0.08/件；中间档位官方表未在本技能内置，需核实",
        "source": "S1 amazon-coach f136（2026 US FBA fulfillment fee 表，核实 2026-09）",
    },
    "large_standard": {
        "desc": "≤20 lb (9.07 kg)，≤18 × 14 × 8 in",
        "anchors": {"≤4 oz": 3.68, "1–1.5 lb": 4.85, "3 lb 以上": 6.05},
        "note": "3 lb 以上为 $6.05 + $0.38/半磅（首磅后）",
        "source": "S1 amazon-coach f136（核实 2026-09）",
    },
    "small_bulky": {
        "desc": "2026 新增档，≤50 lb，37 × 28 × 20 in",
        "anchors": {},
        "note": "费率需核实官方表",
        "source": "S1 amazon-coach f009/f095（分段定义），费率待核实",
    },
    "large_bulky": {
        "desc": "≤50 lb (22.7 kg)，59 × 33 × 33 in",
        "anchors": {"首磅后": "$9.61 + $0.38/lb"},
        "note": "",
        "source": "S1 amazon-coach f136",
    },
}

# 其他 2026 费用参考区间
OTHER_FEES_2026 = {
    "inbound_placement": {
        "small_standard_≤8oz": (0.14, 0.32),
        "small_standard_8-16oz": (0.16, 0.32),
        "note": "多仓拆分可免（≥5 个相同纸箱/托盘）；发往西部仓库通常更贵",
        "source": "S1 amazon-coach f133（2026-01-15 生效）",
    },
    # ★ 低价 FBA 减免：售价 < $10 适用
    "low_price_fba_discount": {
        "threshold_usd": 10.0,
        "discount_range": (0.77, 1.32),
        "note": "售价 < $10 的商品有「低价 FBA」减免，每件约低 $0.77–1.32（按重量档不同）",
        "source": "S1 amazon-coach f136（2026 US FBA fee 表）",
        "important": "★ 这是低货值商品唯一的费用缓冲，测算时不可遗漏",
    },
    "low_inventory_level": {
        "small_standard_≤16oz": {"<14天": 0.89, "14–21天": 0.63, "21–28天": 0.32},
        "large_standard_≤3lb": {"<14天": 0.97, "14–21天": 0.70, "21–28天": 0.36},
        "note": "30/90 天 DOI 同时 <28 天才触发；新品/新卖家有豁免期",
        "source": "S1 amazon-coach f132（2026-01-15 生效）",
    },
    "storage_monthly": {
        "note": "按体积 × 费率；10–12 月旺季约为淡季 2–3 倍。手链类体积极小，通常 <$0.05/月",
        "source": "S1 amazon-coach f096",
    },
    "peak_season": {
        "note": "10/15–次年 1/14 旺季配送费，平均每件 +$0.32，另加 3.5% 燃油与物流附加费",
        "source": "S1 amazon-coach f138",
    },
    "low_value_warning": {
        "threshold_usd": 15.0,
        "note": "★ 客单价 < $15 时，FBA 最低佣金 + 固定配送费会吃掉大部分售价，低货值很难覆盖广告与各项费用",
        "source": "S1 amazon-coach f039（新手选品三大坑之一）",
    },
}

REFERRAL_COMMON = {
    "多数类目": 0.15,
    "电子类": 0.08,
    "珠宝（Jewelry）": 0.20,
    "服装（分档）": "5% / 10% / 17%",
    "note": "整体区间 5%–45%，最低 $0.30/件；珠宝 >$250 的部分降为 5%",
    "source": "S1 amazon-coach f077/f108（Amazon SC Referral fees，核实 2026-09）",
}


def calc_fees(price, referral_rate, fulfillment_fee,
              inbound_placement=0.0, low_inventory=0.0,
              storage_monthly=0.03, return_rate=0.0,
              fulfillment_discount=0.0):
    """
    fulfillment_discount: 低价 FBA 减免金额（售价 <$10 适用），以正数传入，内部按减项处理
    """
    referral = max(price * referral_rate, 0.30)  # 最低 $0.30
    ret = price * return_rate
    items = [
        {"item": "佣金 Referral fee", "amount": round(referral, 2),
         "rate": f"{referral_rate*100:.1f}%", "note": "最低 $0.30/件"},
        {"item": "FBA 配送费", "amount": round(fulfillment_fee, 2), "rate": "-", "note": ""},
        {"item": "入库配置服务费", "amount": round(inbound_placement, 2), "rate": "-",
         "note": "多仓拆分可免"},
        {"item": "低库存水平费", "amount": round(low_inventory, 2), "rate": "-",
         "note": "库存 30–60 天 DOI 可避免"},
        {"item": "月度仓储费", "amount": round(storage_monthly, 2), "rate": "-", "note": ""},
        {"item": "退货损耗", "amount": round(ret, 2), "rate": f"{return_rate*100:.1f}%",
         "note": "经验值，珠宝类目实际可能更高"},
    ]
    if fulfillment_discount:
        items.append({
            "item": "低价 FBA 减免", "amount": round(-fulfillment_discount, 2),
            "rate": "-", "note": "★ 售价 <$10 适用，费用减项"})
    total = sum(i["amount"] for i in items)
    return items, round(total, 2)


def ceiling(price, platform_fee, target_margin, ad_ratio):
    """反推：成本上限（采购 + 头程）"""
    required_gp = price * target_margin
    ad = price * ad_ratio
    max_cost = price - platform_fee - ad - required_gp
    return {
        "target_margin": target_margin,
        "ad_ratio": ad_ratio,
        "required_gross_profit": round(required_gp, 2),
        "ad_cost": round(ad, 2),
        "platform_fee": round(platform_fee, 2),
        "max_purchase_plus_freight": round(max_cost, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price", type=float, required=True)
    ap.add_argument("--category-rate", type=float, required=True,
                    help="佣金率，如 0.20 表示 20%")
    ap.add_argument("--size-tier", default="both",
                    choices=["small_standard", "large_standard", "both"])
    ap.add_argument("--fulfillment-fee", type=float, default=None,
                    help="直接指定 FBA 配送费；省略则用档位锚点")
    ap.add_argument("--inbound-placement", type=float, default=0.25)
    ap.add_argument("--low-inventory", type=float, default=0.0)
    ap.add_argument("--storage-monthly", type=float, default=0.03)
    ap.add_argument("--return-rate", type=float, default=0.04)
    ap.add_argument("--low-price-discount", type=float, default=None,
                    help="低价 FBA 减免金额（正数）。省略时若售价<$10 自动按区间两端做多情景")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    # ★ 低价 FBA 减免判定（售价 <$10 适用）
    lp = OTHER_FEES_2026["low_price_fba_discount"]
    if args.low_price_discount is not None:
        discounts = [args.low_price_discount]
    elif args.price < lp["threshold_usd"]:
        discounts = [0.0, lp["discount_range"][0], lp["discount_range"][1]]
        print(f"★ 售价 ${args.price:.2f} < ${lp['threshold_usd']:.0f} → 适用低价 FBA 减免")
        print(f"  按减免区间 ${lp['discount_range'][0]:.2f} – "
              f"${lp['discount_range'][1]:.2f} 做多情景测算（含「不减免」对照）")
        print()
    else:
        discounts = [0.0]

    lv = OTHER_FEES_2026["low_value_warning"]
    if args.price < lv["threshold_usd"]:
        print(f"⚠ 低货值提示：售价 < ${lv['threshold_usd']:.0f}，"
              f"FBA 最低佣金 + 固定配送费会吃掉大部分售价")
        print(f"  依据：{lv['source']}")
        print()

    tiers = (["small_standard", "large_standard"] if args.size_tier == "both"
             else [args.size_tier])

    print("=" * 74)
    print(f"售价: ${args.price:.2f}   佣金率: {args.category_rate*100:.1f}%")
    print(f"尺寸分段: {args.size_tier}")
    print("=" * 74)

    results = {}
    for tier in tiers:
        info = FBA_FULFILLMENT_2026.get(tier, {})
        anchors = info.get("anchors", {})
        if args.fulfillment_fee is not None:
            fee = args.fulfillment_fee
            fee_basis = "命令行指定"
        elif tier == "small_standard":
            fee = anchors.get("≤2 oz", 3.06)
            fee_basis = "锚点 ≤2 oz（轻小件典型值）"
        elif tier == "large_standard":
            fee = anchors.get("≤4 oz", 3.68)
            fee_basis = "锚点 ≤4 oz（轻小件典型值）"
        else:
            fee = None
            fee_basis = "无内置锚点，需核实"

        items, total = calc_fees(args.price, args.category_rate, fee,
                                 args.inbound_placement, args.low_inventory,
                                 args.storage_monthly, args.return_rate)
        results[tier] = {
            "desc": info.get("desc", ""),
            "fulfillment_fee": fee,
            "fee_basis": fee_basis,
            "fee_source": info.get("source", ""),
            "fee_note": info.get("note", ""),
            "fee_items": items,
            "total_platform_fee": total,
            "fee_pct_of_price": round(total / args.price, 4),
        }

        print(f"\n── 尺寸分段：{tier} ──")
        print(f"  定义: {info.get('desc','')}")
        print(f"  配送费: ${fee if fee else 'N/A'} （{fee_basis}）")
        print(f"  {'费用项':<22}{'金额':>10}   {'比例':<8}备注")
        for it in items:
            print(f"  {it['item']:<22}${it['amount']:>9.2f}   {it['rate']:<8}{it['note']}")
        print(f"  {'平台费用合计':<22}${total:>9.2f}   {total/args.price*100:>6.1f}%")

        # 低价减免情景
        if discounts and discounts != [0.0]:
            print(f"  ── 低价 FBA 减免情景 ──")
            for d in discounts[1:]:
                _, t2 = calc_fees(args.price, args.category_rate, fee,
                                  args.inbound_placement, args.low_inventory,
                                  args.storage_monthly, args.return_rate,
                                  fulfillment_discount=d)
                print(f"  减免 ${d:.2f} 后合计        ${t2:>9.2f}   {t2/args.price*100:>6.1f}%")
            results[tier]["low_price_discount_scenarios"] = [
                {"discount": d,
                 "total": calc_fees(args.price, args.category_rate, fee,
                                    args.inbound_placement, args.low_inventory,
                                    args.storage_monthly, args.return_rate,
                                    fulfillment_discount=d)[1]}
                for d in discounts[1:]
            ]

    # 跨分段差异
    if len(results) == 2:
        d = results["large_standard"]["total_platform_fee"] - results["small_standard"]["total_platform_fee"]
        print(f"\n★ 跨分段差异：Large standard 比 Small standard 每件多 ${d:.2f}")
        print("  → 包装短边若超过 1.9 cm（0.75 in）就跳到 Large standard，这是常被忽略的钱")

    # 成本上限反推
    print("\n" + "=" * 74)
    print("成本上限反推（采购 + 头程 必须 ≤ 此值）")
    print("=" * 74)
    base_tier = tiers[0]
    plat = results[base_tier]["total_platform_fee"]
    ceilings = []
    print(f"  基于分段: {base_tier}，平台费 ${plat:.2f}\n")
    print(f"  {'目标毛利率':<12}{'广告占比':<10}{'需赚毛利':>10}{'广告费':>10}{'成本上限':>12}")
    print("  " + "-" * 62)
    for tm in (0.25, 0.30, 0.35):
        for ar in (0.05, 0.10, 0.15):
            c = ceiling(args.price, plat, tm, ar)
            ceilings.append(c)
            print(f"  {tm*100:>5.0f}%      {ar*100:>5.0f}%     "
                  f"${c['required_gross_profit']:>9.2f}${c['ad_cost']:>9.2f}"
                  f"${c['max_purchase_plus_freight']:>11.2f}")

    print("\n  读法：毛利率 30% + 广告 10% 那一行，就是采购+头程的红线。")
    print("       超过这个数，这个价就做不出来。")

    out = {
        "calculated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "sell_price": args.price,
        "category_rate": args.category_rate,
        "referral_reference": REFERRAL_COMMON,
        "size_tiers": results,
        "ceiling_analysis": ceilings,
        "size_tier_delta": (results["large_standard"]["total_platform_fee"]
                            - results["small_standard"]["total_platform_fee"]
                            if len(results) == 2 else None),
        "other_fees_2026": OTHER_FEES_2026,
        "assumptions": {
            "inbound_placement": args.inbound_placement,
            "low_inventory": args.low_inventory,
            "storage_monthly": args.storage_monthly,
            "return_rate": args.return_rate,
            "note": "这些是假设值；低库存费填 0 表示按『库存管理得当』的情景",
        },
        "data_gaps": {
            "purchase_price": "L3 —— 未知，故只给成本上限",
            "freight": "L3 —— 未知，与采购价合并为上限",
            "packaged_dimensions": "L3 —— 未知，故做跨分段敏感性",
            "actual_acos": "L3 —— 需广告实测（环节 09/10）",
        },
    }

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n已保存 → {args.json}")


if __name__ == "__main__":
    main()
