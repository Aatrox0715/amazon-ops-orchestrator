# 导出与跨 Agent 安装

> **本文是方案，用于讨论。**
> 落地前必须先解决第五节列出的三个兼容性问题 —— 否则"导出"出去也跑不起来。

---

## 一、目标结构（对齐 Agent Skills 通用约定）

大多数 agent（WorkBuddy / CodeBuddy / Claude Code / Codex 等）都遵循同一套目录约定：

```
<skill-name>/
  SKILL.md            ← 必需：YAML frontmatter（name + description）+ 指令正文
  scripts/            ← 可选：可执行脚本
  references/         ← 可选：按需加载的参考文档
  assets/             ← 可选：模板、图片等静态资源
```

**关键约定**：
- `name` 与目录名一致，小写 + 连字符
- `description` 是触发依据 —— 必须写清"什么时候该用这个技能"（含触发词）
- **正文只在被触发时加载**，所以 `SKILL.md` 要精炼，细节放 `references/` 按需读

### 本技能当前结构 vs 目标结构

| 目标位置 | 当前状态 | 需调整 |
|---|---|---|
| `SKILL.md` | ✅ 已有（含 frontmatter） | 需去掉 `agent_created`（WorkBuddy 专有） |
| `scripts/` | ✅ 已有 12 个脚本 | 需**参数化路径** |
| `references/` | ✅ 已有 7 份 | 无需调整 |
| `stages/` | ✅ 已有 10 份 | **非标准目录名** —— 可保留（属 references 语义），也可并入 `references/stages/` |
| `templates/` | ✅ 已有 3 份 | 建议改名为 `assets/`（更符合约定） |
| 根级文档（CHANGELOG / ROADMAP / GETTING-STARTED / EXPORT） | ✅ 已有 | 属元信息，**建议保留但移入 `references/`** 或维持根级 |

---

## 二、组成要素清单（导出前逐项确认）

| # | 要素 | 作用 | 当前状态 |
|---|---|---|---|
| 1 | `SKILL.md` | 触发入口 + 主流程 | ✅ |
| 2 | 环节定义 ×10 | 每环的输入/输出/依赖/契约 | ✅ |
| 3 | 规则文档 ×7 | 闸门、交付规范、来源分级、降级、数值语义 | ✅ |
| 4 | 脚本 ×12 | 抓取 / 测算 / 校验 / 状态管理 | ⚠️ 有硬编码路径 |
| 5 | 模板 ×3 | 状态文件、output 契约、项目骨架 | ⚠️ 缺项目骨架 |
| 6 | **外部依赖声明** | 费率口径来源 | ❌ **未声明为可选依赖** |
| 7 | 版本与变更日志 | 可维护性 | ✅ |
| 8 | 起步指引 | 上手成本 | ✅ |
| 9 | 自查脚本套件 | 质量保证 | ✅（4 层） |
| 10 | **LICENSE** | 分发合规 | ❌ 缺失 |

---

## 三、三种安装方式（按通用性排序）

### 方式 A · 目录复制（最通用，零依赖）

```bash
# WorkBuddy / CodeBuddy
cp -r amazon-ops-orchestrator ~/.workbuddy/skills/

# Claude Code
cp -r amazon-ops-orchestrator ~/.claude/skills/

# 其他遵循该约定的 agent → 放到其 skills 目录
```

**优点**：绝对通用，不依赖任何 CLI
**缺点**：需手动分发，无版本管理

### 方式 B · 技能市场 / CLI 安装（最省事）

```bash
# Vercel Skills CLI
npx skills add <owner>/<repo>@amazon-ops-orchestrator -g -y

# 或 WorkBuddy 内置市场（若上架）
# 通过「设置 — 数据管理 — 应用」或市场搜索安装
```

**优点**：一条命令，自动处理目录与版本
**缺点**：需先上架到某个市场

### 方式 C · Git 仓库分发（最适合团队协作）

```bash
git clone https://<repo>.git
cp -r <repo>/amazon-ops-orchestrator ~/.workbuddy/skills/
```

**优点**：版本可追溯、可协作、可 CI 校验
**缺点**：使用者需会用 git

### 建议组合

**主推 A + C**：把技能放进一个 Git 仓库（便于版本管理与团队同步），
同时提供 ZIP 分发包供不熟悉 git 的人使用（解压即用）。

---

## 四、跨 Agent 兼容性分析

| 兼容点 | 现状 | 风险 |
|---|---|---|
| `SKILL.md` 的 frontmatter | 通用（`name` + `description`） | ✅ 低 |
| `agent_created: true` | **WorkBuddy 专有字段** | ⚠️ 其他 agent 可能报错或忽略 |
| 脚本语言 | Python 3（无第三方依赖） | ✅ 低（但需目标机有 Python） |
| **脚本内的绝对路径** | **硬编码 `C:\Users\10306\...` 与 `E:\workbudyy\...`** | 🔴 **高 —— 换机器直接失效** |
| **外部依赖 `amazon-coach`** | 费率卡来自那个项目 | 🔴 **高 —— 其他环境没有** |
| 编码约定 | 强制 UTF-8（已处理 Windows 控制台） | ✅ 低 |
| 目录名 `stages/` | 非标准 | ⚠️ 中（不影响运行，但与约定不一致） |

---

## 五、导出前必须解决的三个问题

### 问题 1 · 路径硬编码 🔴

**现状**：`state.py` / `crosscheck.py` / `selfcheck.py` 等都写死了项目根目录，例如：

```python
ROOT = r"E:\workbudyy\amazon-ops\projects"
DEFAULT_COACH = r"C:\Users\10306\WorkBuddy\...\amazon-coach\data"
```

**方案**：改为**三级回退**的配置解析

```
1. 命令行参数 --project-root / --coach-dir
2. 环境变量 AMAZON_OPS_ROOT / AMAZON_COACH_DIR
3. 技能目录下的 skill.config.json
4. 兜底：技能目录内的 ./projects
```

**配套**：提供 `skill.config.example.json`，首次使用时复制改名。

### 问题 2 · 外部依赖 amazon-coach 🔴

**现状**：费率与规范口径（20 张卡）来自那个项目，且 `dep_check.py` 依赖它。

**方案**：**把它从"硬依赖"改为"可选增强"**

| 层 | 内容 | 是否必需 |
|---|---|---|
| **内置最小费率表** | 佣金率 / FBA 费用档位 / 尺寸分段 / 字符规范 等**关键常量** | ✅ 必需（随技能分发） |
| **扩展到 amazon-coach** | 141 张卡的完整知识库 + 时效管理 | ⚪ 可选（检测到则启用） |

`dep_check.py` 在没有 amazon-coach 时应**降级为"检查内置费率表的版本日期"**，而不是报错。

### 问题 3 · 专有字段与目录名 ⚠️

- 去掉或条件化 `agent_created`
- `templates/` → 改名 `assets/`（可选，更合约定）
- 根级元信息文档（CHANGELOG / ROADMAP / GETTING-STARTED / EXPORT）：
  建议移入 `references/` 并在 `SKILL.md` 里给出索引，保持根目录干净

---

## 六、分发包形态建议

```
amazon-ops-orchestrator-0.5.0.zip
├── amazon-ops-orchestrator/
│   ├── SKILL.md
│   ├── skill.config.example.json     ← 配置模板
│   ├── references/
│   │   ├── 00-flow-map.md … 06-numeric-semantics.md
│   │   └── meta/                     ← 根级文档移入
│   │       ├── CHANGELOG.md
│   │       ├── ROADMAP.md
│   │       ├── GETTING-STARTED.md
│   │       └── EXPORT.md
│   ├── stages/                       ← 10 份环节定义
│   ├── assets/                       ← 原 templates/
│   ├── scripts/                      ← 12 个脚本（已参数化）
│   ├── tests/                        ← 回归测试
│   └── LICENSE
└── README.md                          ← 安装说明（面向使用者）
```

---

## 七、导出的前置条件（按顺序）

| # | 前置条件 | 优先级 |
|---|---|---|
| 1 | 脚本路径参数化（三级回退） | 🔴 必须 |
| 2 | 内置最小费率表 + amazon-coach 降级为可选 | 🔴 必须 |
| 3 | 补 `LICENSE` | 🟡 建议 |
| 4 | 补 `skill.config.example.json` | 🟡 建议 |
| 5 | 去掉/条件化 `agent_created` | 🟡 建议 |
| 6 | 加回归测试（ROADMAP 的 P1-4） | 🟢 可选 |
| 7 | 目录名与约定对齐（templates → assets） | 🟢 可选 |

**只做 1、2 就能保证"换个环境能用"；做完 3–7 才算"规范可分发"。**

---

## 八、待讨论的决策点

1. **分发包形态**：Git 仓库 / ZIP / 两者都要？
2. **外部依赖策略**：内置最小费率表（推荐）还是要求必须配 amazon-coach？
3. **目录结构**：是否按第六节重组（根级文档移入 references）？
4. **是否上架市场**：如果上架，需要额外做合规与描述优化
5. **是否开源**：影响 LICENSE 选择与是否需要脱敏
