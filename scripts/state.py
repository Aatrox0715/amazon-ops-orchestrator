#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
amazon-ops-orchestrator 状态管理 CLI

用法：
  python state.py roots
  python state.py new <代号> [--name 产品名] [--market US]
  python state.py list
  python state.py show <代号>
  python state.py stage <代号> <环节号> <状态> [--output 路径]
  python state.py confirm <代号> "<决策文本>"
  python state.py level <代号> <L1|L2|L3>
  python state.py missing <代号> add "<字段名>" "<原因>" ["<降级方式>"]
  python state.py missing <代号> clear

状态取值：pending | in_progress | awaiting_gate | done | skipped
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── 统一配置（三级回退，替代硬编码路径）──
try:
    from _config import (project_root, coach_dir, SKILL_ROOT,
                         coach_mode, load_config, CONFIG_PATH)
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from _config import (project_root, coach_dir, SKILL_ROOT,
                         coach_mode, load_config, CONFIG_PATH)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = project_root()
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "assets", "_state.template.json")

TZ = timezone(timedelta(hours=8))
VALID_STATUS = {"pending", "in_progress", "awaiting_gate", "done", "skipped"}


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def state_path(code):
    return os.path.join(ROOT, code, "_state.json")


def load(code):
    p = state_path(code)
    if not os.path.isfile(p):
        die(f"项目 {code} 不存在。用 new 新建，或 list 看看有哪些项目。")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(code, data):
    data["updated_at"] = now()
    p = state_path(code)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存 {p}")


def die(msg, code_=1):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(code_)


def cmd_new(args):
    if not args:
        die("缺少项目代号。用法：state.py new <代号>")
    code = args[0]
    name = opt(args, "--name", "")
    market = opt(args, "--market", "US")

    if os.path.isfile(state_path(code)):
        die(f"项目 {code} 已存在。换个代号，或先 show {code} 看看。")

    with open(TEMPLATE, encoding="utf-8") as f:
        st = json.load(f)
    st["project"] = code
    st["product_name"] = name or code
    st["target_marketplace"] = market
    st["created_at"] = now()

    for sub in ["01-市场调研", "02-竞品拆解"]:
        os.makedirs(os.path.join(ROOT, code, sub), exist_ok=True)

    save(code, st)
    print(f"项目已创建：{code}（{st['product_name']}，站点 {market}）")
    print(f"目录：{os.path.join(ROOT, code)}")


def cmd_list(_args):
    if not os.path.isdir(ROOT):
        print("还没有任何项目。")
        return
    codes = sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))
    if not codes:
        print("还没有任何项目。")
        return
    print(f"{'代号':<20}{'产品名':<20}{'当前':<6}{'数据源':<8}进度")
    print("-" * 70)
    for c in codes:
        try:
            st = load(c)
        except SystemExit:
            continue
        done = sum(1 for v in st["stages"].values() if v["status"] == "done")
        print(
            f"{c:<20}{st.get('product_name',''):<20}"
            f"{st.get('current_stage',''):<6}{st.get('data_source_level',''):<8}"
            f"{done}/10"
        )


def cmd_show(args):
    code = need_code(args)
    st = load(code)
    print(f"项目：{st['project']}  ({st.get('product_name','')})")
    print(f"站点：{st.get('target_marketplace','')}   数据源级别：{st.get('data_source_level','')}")
    print(f"创建：{st.get('created_at','')}   更新：{st.get('updated_at','')}")
    print(f"当前环节：{st.get('current_stage','')}")
    print()
    print(f"{'环节':<5}{'名称':<18}{'闸门':<6}{'状态':<16}完成时间")
    print("-" * 72)
    for k, v in sorted(st["stages"].items()):
        flag = "  ← 当前" if k == st.get("current_stage") else ""
        print(
            f"{k:<5}{v['name']:<18}{v['gate']:<6}{v['status']:<16}"
            f"{v.get('completed_at') or '-'}{flag}"
        )
    if st.get("missing_fields"):
        print(f"\nL3 缺失字段（{len(st['missing_fields'])} 项）：")
        for m in st["missing_fields"]:
            print(f"  - {m.get('field')}：{m.get('reason','')}")
    if st.get("confirmed_by_user"):
        print(f"\n已确认决策（{len(st['confirmed_by_user'])} 条）：")
        for c in st["confirmed_by_user"][-5:]:
            print(f"  [{c.get('at','')[:10]}] {c.get('decision','')}")
    if st.get("revision_history"):
        print(f"\n修订记录：{len(st['revision_history'])} 次")


def cmd_stage(args):
    if len(args) < 3:
        die("用法：state.py stage <代号> <环节号> <状态> [--output 路径]")
    code, key, status = args[0], args[1].zfill(2), args[2]
    if status not in VALID_STATUS:
        die(f"状态必须是 {sorted(VALID_STATUS)} 之一")
    st = load(code)
    if key not in st["stages"]:
        die(f"环节号 {key} 不存在（01-10）")
    st["stages"][key]["status"] = status
    if status == "done":
        st["stages"][key]["completed_at"] = now()
    out = opt(args, "--output", None)
    if out:
        st["stages"][key]["output"] = out
    nxt = [k for k in sorted(st["stages"]) if st["stages"][k]["status"] not in ("done", "skipped")]
    st["current_stage"] = nxt[0] if nxt else "全部完成"
    save(code, st)
    print(f"环节 {key} {st['stages'][key]['name']} → {status}")


def cmd_confirm(args):
    if len(args) < 2:
        die('用法：state.py confirm <代号> "<决策文本>"')
    code, decision = args[0], args[1]
    st = load(code)
    st["confirmed_by_user"].append({"decision": decision, "at": now()})
    save(code, st)
    print(f"已记录决策：{decision}")


def cmd_level(args):
    if len(args) < 2:
        die("用法：state.py level <代号> <L1|L2|L3>")
    code, lv = args[0], args[1].upper()
    if lv not in ("L1", "L2", "L3"):
        die("级别必须是 L1 / L2 / L3")
    st = load(code)
    st["data_source_level"] = lv
    save(code, st)
    print(f"数据源级别 → {lv}")


def cmd_missing(args):
    if len(args) < 2:
        die('用法：state.py missing <代号> add "<字段>" "<原因>" ["<降级方式>"] | clear')
    code, action = args[0], args[1]
    st = load(code)
    if action == "clear":
        st["missing_fields"] = []
    elif action == "add":
        rest = args[2:]
        if len(rest) < 2:
            die('add 需要：字段名 和 原因')
        st["missing_fields"].append(
            {"field": rest[0], "reason": rest[1],
             "degraded_to": rest[2] if len(rest) > 2 else ""}
        )
    else:
        die("action 只能是 add 或 clear")
    save(code, st)
    print(f"L3 缺失字段现有 {len(st['missing_fields'])} 项")


def cmd_roots(args):
    """打印所有生效路径及其**解析来源** —— 排查「配置没生效」类问题的第一入口"""
    cfg = load_config()
    has_cfg_file = os.path.isfile(CONFIG_PATH)

    # 逐层判定来源
    env_root = os.environ.get("AMAZON_OPS_ROOT")
    if env_root:
        src_root = "环境变量 AMAZON_OPS_ROOT"
    elif cfg.get("project_root"):
        src_root = "skill.config.json → project_root"
    else:
        src_root = "兜底：技能目录内 projects/"

    mode, coach_path, coach_msg = coach_mode()
    env_coach = os.environ.get("AMAZON_COACH_DIR")
    if env_coach:
        src_coach = "环境变量 AMAZON_COACH_DIR"
    elif cfg.get("coach_dir"):
        src_coach = "skill.config.json → coach_dir"
    else:
        src_coach = "兜底：技能自带 data/"

    root = project_root()
    print("路径解析结果")
    print("─" * 70)
    print(f"  技能根目录   {SKILL_ROOT}")
    print()
    print(f"  项目根目录   {root}")
    print(f"    来源       {src_root}")
    exists = os.path.isdir(root)
    print(f"    状态       {'存在' if exists else '不存在（首次运行会自动创建）'}")
    if exists:
        subs = sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))
        print(f"    项目数     {len(subs)}" + (f"  → {', '.join(subs[:8])}" if subs else "  （尚无项目）"))
    print()
    print(f"  知识库       {coach_path}")
    print(f"    来源       {src_coach}")
    print(f"    模式       {mode} —— {coach_msg}")
    print()
    print(f"  配置文件     {CONFIG_PATH}")
    print(f"               {'已创建' if has_cfg_file else '未创建（可复制 skill.config.example.json）'}")
    print()
    print("提示：若「来源」不是你以为的那层，说明更高优先级的层在生效，")
    print("      或被 skill.config.json 覆盖 —— 按上面的顺序逐层排查。")


def need_code(args):
    if not args:
        die("缺少项目代号")
    return args[0]


def opt(args, flag, default):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return default


COMMANDS = {
    "roots": cmd_roots,
    "new": cmd_new, "list": cmd_list, "show": cmd_show,
    "stage": cmd_stage, "confirm": cmd_confirm,
    "level": cmd_level, "missing": cmd_missing,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        die(f"未知命令 {cmd}。可用：{sorted(COMMANDS)}")
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
