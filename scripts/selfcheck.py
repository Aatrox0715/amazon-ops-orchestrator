#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目产出自查：检查交付物完整性、契约一致性、L3 标注合规

用法：
  python selfcheck.py <项目代号>
  python selfcheck.py <项目代号> --skill-dir <技能目录>   # 同时检查技能文件完整性

检查项：
  A. 技能自检 —— 10 环定义文件、references、scripts 是否齐全
  B. 项目自检 —— 每环三件套是否齐全、output.json 是否合法
  C. 契约自检 —— output.json 是否含 sources / missing_fields / payload 三要素
  D. L3 自检 —— 缺失字段是否都写了 reason 与降级方式
  E. 决策自检 —— P1 闸门环节是否有 confirmed / selected 留痕
  F. 状态自检 —— _state.json 与实际产出是否一致
"""
import argparse
import json
import os
import sys
import zipfile
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
DEFAULT_SKILL = SKILL_ROOT
TZ = timezone(timedelta(hours=8))

STAGES = {
    "01": ("市场调研", "01-市场调研", "P2"),
    "02": ("竞品拆解", "02-竞品拆解", "P2"),
    "03": ("评论与VOC分析", "03-评论与VOC分析", "P2"),
    "04": ("关键词库搭建", "04-关键词库", "P1"),
    "05": ("定价与利润测算", "05-定价利润", "P1"),
    "06": ("Listing文案编写", "06-文案", "P1"),
    "07": ("视觉素材规划", "07-视觉素材", "P1"),
    "08": ("合规与质量体检", "08-合规体检", "P1"),
    "09": ("广告架构规划", "09-广告架构", "P1"),
    "10": ("复盘与迭代", "10-复盘迭代", "P2→P1"),
}

REQUIRED_SKILL_FILES = [
    # 根级
    "SKILL.md", "README.md", "LICENSE", "CHANGELOG.md",
    "skill.config.example.json", ".gitignore",
    # 面向使用者的文档
    "docs/getting-started.md", "docs/roadmap.md", "docs/exporting.md",
    # 规则与规范
    "references/00-flow-map.md", "references/01-gates.md",
    "references/02-deliverable-spec.md", "references/03-source-grading.md",
    "references/04-data-source-ladder.md", "references/05-sop-index.md",
    "references/06-numeric-semantics.md",
    # 10 个环节定义
    "stages/stage-01-market.md", "stages/stage-02-competitor.md",
    "stages/stage-03-voc.md", "stages/stage-04-keyword.md",
    "stages/stage-05-pricing.md", "stages/stage-06-listing.md",
    "stages/stage-07-visual.md", "stages/stage-08-compliance.md",
    "stages/stage-09-ads.md", "stages/stage-10-review.md",
    # 模板（assets/）
    "assets/_state.template.json", "assets/output.template.json",
    # 自带离线卡片集
    "data/min-cards.json",
    # 脚本
    "scripts/_config.py", "scripts/state.py", "scripts/fetch_listing.py",
    "scripts/fetch_reviews.py", "scripts/fetch_suggestions.py",
    "scripts/pricing_calc.py", "scripts/listing_check.py",
    "scripts/make_xlsx.py", "scripts/selfcheck.py", "scripts/crosscheck.py",
    "scripts/semantic_check.py", "scripts/report_check.py", "scripts/dep_check.py",
]

CONTRACT_KEYS = ["stage", "stage_name", "project", "data_source_level",
                 "sources", "missing_fields", "payload"]


class Checker:
    def __init__(self):
        self.pass_, self.warn, self.fail = [], [], []

    def ok(self, m):
        self.pass_.append(m)

    def w(self, m):
        self.warn.append(m)

    def f(self, m):
        self.fail.append(m)


def check_skill(c, skill_dir):
    print("─" * 74)
    print("A. 技能文件完整性")
    print("─" * 74)
    miss = []
    for rel in REQUIRED_SKILL_FILES:
        p = os.path.join(skill_dir, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            miss.append(rel)
    if miss:
        c.f(f"技能缺失 {len(miss)} 个文件：{', '.join(miss)}")
        for m in miss:
            print(f"   ✗ {m}")
    else:
        c.ok(f"技能文件齐全（{len(REQUIRED_SKILL_FILES)} 个）")
        print(f"   ✓ {len(REQUIRED_SKILL_FILES)} 个文件全部存在")


def check_project(c, code, project_dir):
    print()
    print("─" * 74)
    print("B. 项目三件套完整性")
    print("─" * 74)

    st_path = os.path.join(project_dir, "_state.json")
    if not os.path.isfile(st_path):
        c.f("缺少 _state.json")
        print("   ✗ _state.json 不存在")
        return None
    st = json.load(open(st_path, encoding="utf-8"))
    print(f"   {'环节':<5}{'名称':<18}{'状态':<12}{'output.json':<14}{'report.md':<12}{'data.xlsx'}")
    print("   " + "-" * 70)

    for k in sorted(STAGES):
        name, d, gate = STAGES[k]
        status = st["stages"].get(k, {}).get("status", "?")
        sd = os.path.join(project_dir, d)

        if status in ("pending",):
            print(f"   {k:<5}{name:<18}{status:<12}{'—':<14}{'—':<12}—")
            continue

        has_d = os.path.isdir(sd)
        oj = os.path.isfile(os.path.join(sd, "output.json"))
        rm = os.path.isfile(os.path.join(sd, "report.md"))
        xl = os.path.isfile(os.path.join(sd, "data.xlsx"))

        flag = lambda b: "✓" if b else "✗"
        print(f"   {k:<5}{name:<18}{status:<12}{flag(oj):<14}{flag(rm):<12}{flag(xl)}")

        if status == "done":
            if not has_d:
                c.f(f"环节 {k} 标为 done 但目录不存在")
            if not oj:
                c.f(f"环节 {k} 标为 done 但缺 output.json")
            if not rm:
                c.f(f"环节 {k} 标为 done 但缺 report.md")
            if not xl:
                c.w(f"环节 {k} 缺 data.xlsx（若该环节非数据密集型可接受）")

        # output.json 契约
        if oj:
            try:
                d = json.load(open(os.path.join(sd, "output.json"), encoding="utf-8"))
            except Exception as e:
                c.f(f"环节 {k} 的 output.json 解析失败：{e}")
                continue
            miss = [x for x in CONTRACT_KEYS if x not in d]
            if miss:
                c.w(f"环节 {k} 的 output.json 缺契约字段：{', '.join(miss)}")
            else:
                c.ok(f"环节 {k} 契约完整")

            # L3 标注检查
            mf = d.get("missing_fields") or []
            bad = [m for m in mf if not m.get("reason") or
                   not (m.get("degraded_to") or m.get("degrade") or m.get("fallback"))]
            if bad:
                c.w(f"环节 {k} 有 {len(bad)} 条 L3 缺失未写全 reason/degraded_to")
            if mf:
                c.ok(f"环节 {k} 记录 {len(mf)} 条 L3 缺失")

            # 闸门留痕检查
            if gate.startswith("P1"):
                conf = d.get("confirmed_by_user") or []
                has_sel = any(d.get("payload", {}).get(x) is not None for x in
                              ("selected_strategy", "selected_option",
                               "selected_title_option", "finalized"))
                if not conf and not has_sel:
                    c.f(f"环节 {k} 是 P1 闸门但未见决策留痕")
                else:
                    c.ok(f"环节 {k}（P1）决策已留痕")
    return st


def check_xlsx(c, project_dir):
    print()
    print("─" * 74)
    print("C. xlsx 文件有效性")
    print("─" * 74)
    import glob
    files = sorted(glob.glob(os.path.join(project_dir, "*", "data.xlsx")))
    for p in files:
        try:
            z = zipfile.ZipFile(p)
            if z.testzip() is not None:
                c.f(f"{os.path.basename(os.path.dirname(p))} 的 xlsx zip 损坏")
                print(f"   ✗ {os.path.basename(os.path.dirname(p))}")
            else:
                print(f"   ✓ {os.path.basename(os.path.dirname(p)):<16}"
                      f"{os.path.getsize(p):>7d} bytes")
                c.ok(f"{os.path.basename(os.path.dirname(p))} xlsx 有效")
        except Exception as e:
            c.f(f"{os.path.basename(os.path.dirname(p))} xlsx 打开失败：{e}")


def check_state(c, st):
    print()
    print("─" * 74)
    print("D. 状态一致性")
    print("─" * 74)
    if not st:
        return
    done = sum(1 for v in st["stages"].values() if v["status"] == "done")
    skip = sum(1 for v in st["stages"].values() if v["status"] == "skipped")
    pend = sum(1 for v in st["stages"].values() if v["status"] == "pending")
    print(f"   done={done}  skipped={skip}  pending={pend}")
    print(f"   数据源级别：{st.get('data_source_level')}")
    print(f"   L3 缺失：{len(st.get('missing_fields', []))} 条")
    print(f"   决策记录：{len(st.get('confirmed_by_user', []))} 条")
    c.ok(f"{done} 环完成 / {skip} 环跳过 / {pend} 环待办")
    if pend:
        c.w(f"仍有 {pend} 环未处理")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--skill-dir", default=DEFAULT_SKILL)
    args = ap.parse_args()

    code = args.project
    project_dir = os.path.join(ROOT, code)
    if not os.path.isdir(project_dir):
        print(f"错误：项目 {code} 不存在", file=sys.stderr)
        sys.exit(1)

    print("=" * 74)
    print(f"项目产出自查 · {code}")
    print(f"时间：{datetime.now(TZ).isoformat(timespec='seconds')}")
    print("=" * 74)

    c = Checker()
    check_skill(c, args.skill_dir)
    st = check_project(c, code, project_dir)
    check_xlsx(c, project_dir)
    check_state(c, st)

    print()
    print("=" * 74)
    print("自查结论")
    print("=" * 74)
    print(f"  ✅ 通过 {len(c.pass_)} 项")
    if c.warn:
        print(f"  ⚠️  警告 {len(c.warn)} 项")
        for m in c.warn:
            print(f"     · {m}")
    if c.fail:
        print(f"  ❌ 失败 {len(c.fail)} 项")
        for m in c.fail:
            print(f"     · {m}")
    print()
    verdict = "通过" if not c.fail else "存在问题"
    print(f"  总体：{'✅ ' + verdict if not c.fail else '❌ ' + verdict}")
    print("=" * 74)
    return 0 if not c.fail else 1


if __name__ == "__main__":
    sys.exit(main())
