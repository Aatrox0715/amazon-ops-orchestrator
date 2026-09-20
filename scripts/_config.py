#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一配置解析（三级回退）

解决的问题：
  原脚本把路径写死（`E:\\workbudyy\\...` / `C:\\Users\\10306\\...`），
  换一台机器就会失效。本模块提供与运行环境无关的路径解析。

路径解析优先级：
  1. 命令行参数
  2. 环境变量（AMAZON_OPS_ROOT / AMAZON_COACH_DIR）
  3. 技能根目录下的 skill.config.json
  4. 兜底：技能目录内的 ./projects 与 ./data

用法：
  from _config import project_root, coach_dir, require_coach, skill_root
"""
import json
import os
import sys

# 技能根目录：本文件位于 <skill>/scripts/ 下
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_ROOT, "skill.config.json")
EXAMPLE_PATH = os.path.join(SKILL_ROOT, "skill.config.example.json")

_cache = None


def load_config():
    global _cache
    if _cache is not None:
        return _cache
    cfg = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f) or {}
        except Exception:
            cfg = {}
    _cache = cfg
    return cfg


def reload_config():
    global _cache
    _cache = None
    return load_config()


def skill_root():
    return SKILL_ROOT


def project_root(cli=None):
    """项目产出根目录"""
    if cli:
        return os.path.abspath(cli)
    env = os.environ.get("AMAZON_OPS_ROOT")
    if env:
        return os.path.abspath(env)
    cfg = load_config().get("project_root")
    if cfg:
        return os.path.abspath(os.path.expanduser(cfg))
    return os.path.join(SKILL_ROOT, "projects")


def coach_dir(cli=None):
    """
    amazon-coach 数据目录（**必需依赖**）

    本项目要求集成 amazon-coach 的费率与规范口径。
    若未配置外部目录，则回退到技能自带的 `data/`（离线最小卡片集）。
    """
    if cli:
        return os.path.abspath(cli)
    env = os.environ.get("AMAZON_COACH_DIR")
    if env:
        return os.path.abspath(env)
    cfg = load_config().get("coach_dir")
    if cfg:
        return os.path.abspath(os.path.expanduser(cfg))
    # 兜底：技能自带
    return os.path.join(SKILL_ROOT, "data")


def coach_mode():
    """
    返回 ('外部' | '内置', 路径, 说明)
    外部：指向真实的 amazon-coach（141 张卡 + 时效管理）
    内置：技能自带的离线最小卡片集（20 张必需卡）
    """
    cfg_path = None
    if load_config().get("coach_dir"):
        cfg_path = os.path.abspath(os.path.expanduser(load_config()["coach_dir"]))
    elif os.environ.get("AMAZON_COACH_DIR"):
        cfg_path = os.path.abspath(os.environ["AMAZON_COACH_DIR"])

    if cfg_path and os.path.isfile(os.path.join(cfg_path, "flashcards.json")):
        return "外部", cfg_path, "已集成外部 amazon-coach（完整知识库）"

    builtin = os.path.join(SKILL_ROOT, "data")
    if os.path.isfile(os.path.join(builtin, "flashcards.json")):
        return "内置", builtin, "使用技能自带的离线卡片集"
    if os.path.isfile(os.path.join(builtin, "min-cards.json")):
        return "内置", builtin, "使用技能自带的离线最小卡片集"
    return "缺失", builtin, "找不到任何卡片数据源"


def require_coach(strict=False):
    """
    检查 amazon-coach 依赖是否可用。

    strict=True 时，若用的是内置集而非外部完整库，视为不满足（返回 False）。
    本项目**要求集成**，但为开源可用性保留了内置兜底 —— 由调用方决定严格程度。
    """
    mode, path, msg = coach_mode()
    if mode == "缺失":
        return False, path, (
            "未找到 amazon-coach 数据源。\n"
            f"  请任选其一：\n"
            f"    ① 设置环境变量 AMAZON_COACH_DIR=<amazon-coach/data 路径>\n"
            f"    ② 在 {CONFIG_PATH} 里配置 \"coach_dir\"\n"
            f"    ③ 直接使用技能自带的 data/（已被清空或缺失）\n"
            f"  配置模板见 {EXAMPLE_PATH}"
        )
    if strict and mode != "外部":
        return False, path, f"要求集成外部 amazon-coach，当前为{msg}"
    return True, path, msg


def flashcards_path():
    """返回可用的 flashcards.json 路径（外部优先，其次内置）"""
    d = coach_dir()
    for name in ("flashcards.json", "min-cards.json"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def ensure_utf8_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def describe():
    """打印当前配置（供调试）"""
    mode, path, msg = coach_mode()
    print(f"  技能根目录 : {skill_root()}")
    print(f"  项目根目录 : {project_root()}")
    print(f"  coach 模式 : {mode}  ({path})")
    print(f"              {msg}")
    print(f"  配置文件   : {CONFIG_PATH}  {'[存在]' if os.path.isfile(CONFIG_PATH) else '[未创建，用 example 复制]'}")


if __name__ == "__main__":
    ensure_utf8_stdout()
    print("当前解析结果：")
    describe()
