# 导出与跨 Agent 安装

> **状态：已落地。** 本文说明如何把本技能安装到其他 agent，以及分发时的注意事项。
> 历史方案与决策记录见 `CHANGELOG.md`。

---

## 一、目录约定（对齐 Agent Skills 通用形态）

大多数 agent（WorkBuddy / CodeBuddy / Claude Code / Codex 等）遵循同一套目录约定：

```
<skill-name>/
  SKILL.md            ← 必需：YAML frontmatter（name + description）+ 指令正文
  scripts/            ← 可选：可执行脚本
  references/         ← 可选：按需加载的参考文档
  assets/             ← 可选：模板、图片等静态资源
```

**关键约定**

- `name` 必须与目录名一致，小写 + 连字符
- `description` 是**唯一触发依据** —— 写清"什么时候该用"，并把触发词列全
- 正文只在被触发时加载，因此 `SKILL.md` 保持精炼，细节放进 `references/` 按需读

### 本技能的实际结构

```
amazon-ops-orchestrator/
├── SKILL.md                  触发入口 + 启动协议 + 路由表
├── README.md                 项目说明
├── LICENSE                   MIT
├── CHANGELOG.md              版本变更
├── skill.config.example.json 配置模板（复制为 skill.config.json 使用）
├── .gitignore / .gitattributes
├── docs/
│   ├── getting-started.md    起步指引
│   ├── roadmap.md            成熟度与改进路线
│   └── exporting.md          本文
├── references/               7 份规则文档（闸门 / 交付规范 / 来源分级 / 降级 / 数值语义 / SOP 索引 / 流程图）
├── stages/                   10 份环节定义
├── scripts/                  13 个脚本（全部 import _config）
├── assets/                   2 个模板（状态文件 / output 契约）
├── data/min-cards.json       离线兜底卡片集（20 张必需卡）
└── tests/                    回归测试目录（待补）
```

**说明**：`stages/` 与 `docs/` 是非标准目录名，但属 `references` 语义的合理拆分；
它们**不影响运行**，仅在被读取时按需加载。保留是为了让 10 个环节的定义独立可读。

---

## 二、三种安装方式

### 方式 A · 目录复制（最通用，零依赖）

```bash
git clone https://github.com/Aatrox0715/amazon-ops-orchestrator.git

# WorkBuddy / CodeBuddy
cp -r amazon-ops-orchestrator ~/.workbuddy/skills/

# Claude Code
cp -r amazon-ops-orchestrator ~/.claude/skills/

# 其他遵循该约定的 agent → 放进其 skills 目录
```

**优点**：绝对通用，不依赖任何 CLI
**缺点**：手动分发，无版本管理

### 方式 B · 技能市场 / CLI 安装

```bash
npx skills add <owner>/<repo>@amazon-ops-orchestrator -g -y
```

**优点**：一条命令，自动处理目录与版本
**缺点**：需先上架到某个市场（**本项目未上架**，见下文）

### 方式 C · Git 仓库分发（适合协作与迭代）

```bash
git clone https://github.com/Aatrox0715/amazon-ops-orchestrator.git
cp -r amazon-ops-orchestrator ~/.workbuddy/skills/
```

**优点**：版本可追溯、可协作、可 CI 校验
**缺点**：使用者需会用 git

### 推荐

**A + C 组合**：放进 Git 仓库便于版本管理，同时出 ZIP 包供不熟悉 git 的人解压即用。

---

## 三、安装后配置（可选，但推荐）

技能**零配置即可运行** —— 自带 `data/min-cards.json`（20 张必需卡）。
配置外部知识库可解锁完整能力（141 张卡 + 时效管理）。

```bash
cd <技能目录>
cp skill.config.example.json skill.config.json
# 编辑 skill.config.json，填入 project_root 与 coach_dir
```

**路径解析优先级**（先命中者胜，所有脚本共用 `scripts/_config.py`）：

| 顺序 | 来源 | 说明 |
|---|---|---|
| 1 | 命令行参数 | `--project-root` / `--coach-dir` |
| 2 | 环境变量 | `AMAZON_OPS_ROOT` / `AMAZON_COACH_DIR` |
| 3 | `skill.config.json` | 技能根目录下 |
| 4 | 兜底 | 技能目录内的 `projects/` 与 `data/` |

**排查配置问题的第一入口**：

```bash
python scripts/state.py roots
```

它会打印每一层的**实际生效值与来源**，而不是只给一个路径 —— 配置没生效时能立刻看出是被哪一层覆盖了。

---

## 四、跨 Agent 兼容性

| 兼容点 | 状态 | 说明 |
|---|---|---|
| `SKILL.md` 的 frontmatter | ✅ | 仅用 `name` + `description` 等通用字段 |
| `agent_created: true` | ⚠️ | **WorkBuddy 专有**。其他 agent 会忽略未知字段，不影响运行；如需完全中立可删除 |
| 脚本语言 | ✅ | Python 3，**无第三方依赖**（目标机需有 Python 3.8+） |
| 脚本内的绝对路径 | ✅ | 已全部改为 `_config.py` 三级回退，**无残留** |
| 外部依赖 `amazon-coach` | ✅ | 已改为「可选增强 + 内置兜底」，缺失时自动降级，不报错 |
| 编码约定 | ✅ | 强制 UTF-8（已处理 Windows 控制台） |
| 目录名 `stages/` `docs/` | ⚠️ | 非标准名，但不影响运行 |
| `data/` 目录 | ⚠️ | 非标准名，属资源目录，不影响运行 |

**结论**：可直接安装到任何遵循 skills 约定的 agent，**零配置可跑**。

---

## 五、分发前的自检

```bash
python scripts/selfcheck.py <项目代号>      # 文件层
python scripts/crosscheck.py <项目代号>     # 内容层
python scripts/semantic_check.py <项目代号> # 基数层
python scripts/report_check.py <项目代号>   # 报数层
python scripts/dep_check.py                 # 依赖时效
python scripts/state.py roots               # 路径解析自检
```

**分发审计**：确认包内无本机路径泄漏、无本地配置入库：

```bash
git grep -n -E "C:\\\\Users|<你的用户名>|/home/<用户名>" -- .   # 应无输出
git status --short --ignored                                  # 确认 skill.config.json 与 projects/ 被忽略
```

---

## 六、ZIP 分发包形态

```
amazon-ops-orchestrator-<version>.zip
└── amazon-ops-orchestrator/
    ├── SKILL.md
    ├── README.md
    ├── LICENSE
    ├── CHANGELOG.md
    ├── skill.config.example.json
    ├── docs/  references/  stages/  scripts/  assets/  data/  tests/
    └── （不含 skill.config.json 与 projects/ —— 本地数据不入包）
```

**打包命令**：

```bash
git archive --format=zip --prefix=amazon-ops-orchestrator/ \
    -o amazon-ops-orchestrator-0.5.0.zip HEAD
```

用 `git archive` 而非直接压缩目录 —— 它**只打包已纳入版本控制的文件**，
自动排除 `skill.config.json`、`projects/`、`__pycache__` 等本地内容，无需人工检查。

---

## 七、明确不做的事

| 项 | 原因 |
|---|---|
| **不上架技能市场** | 项目以 Git 仓库形式开源分发，见 `README.md` |
| **不提供内置完整费率表** | 费率口径统一由外部 `amazon-coach` 提供，避免两处维护产生分歧；离线场景用 `data/min-cards.json` 兜底 |
| **不引入第三方 Python 依赖** | 保证任何有 Python 3 的环境都能直接跑，无需 pip |
