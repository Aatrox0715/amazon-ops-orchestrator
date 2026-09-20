# amazon-ops-orchestrator

> 亚马逊运营全流程分析技能 —— 一套给 AI agent 用的十环工作流

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](CHANGELOG.md)

---

## 这是什么

**一个流程调度器，不是知识库。**

它让 AI agent 在你提出亚马逊运营需求时，按一套结构化的十环流程干活：
自己判断该走哪一环、需要什么输入、在哪些节点停下来等你拍板。

覆盖从**竞品拆解**到**广告复盘**的完整链路：

```
01 市场调研 → 02 竞品拆解 → 03 评论VOC → 04 关键词库 → 05 定价利润
           → 06 文案编写 → 07 视觉规划 → 08 合规体检 → 09 广告架构 → 10 复盘迭代
```

---

## 核心特性

### 1. 三条贯穿全程的准则

- **不编造** —— 拿不到的数据写空并标注级别，不用估算值充数
- **来源必标** —— 每个事实性数字带来源与核实日期
- **关键节点停下** —— 高风险环节设确认闸门，不自行定稿

### 2. 数据源三级降级

| 级别 | 条件 | 行为 |
|---|---|---|
| L1 | 有授权账号 / 卖家后台 | 自动拉取 |
| L2 | 无账号，公开可获取 | 抓取 / 反推（多数量化值会缺） |
| L3 | 完全拿不到 | **显式标注缺失，不编造** |

**同一份交付物模板在三级下结构不变** —— 数据源升级后只换填充方式，不用重做。

### 3. 四层自查体系

| 层 | 脚本 | 验什么 |
|---|---|---|
| 文件层 | `selfcheck.py` | 三件套完整性、契约字段、表格有效性 |
| 内容层 | `crosscheck.py` | 跨环节数字一致、引用链、观察闭环 |
| **基数层** | `semantic_check.py` | **币种 / 单位 / 量纲 / 假设标注** |
| 报数层 | `report_check.py` | 报告是否残留已作废的值 |

**为什么基数层必须单独存在**：本项目在实战中发生过售价币种读错
（把 `CNY 66.88` 当成 `$66.88`，放大 6.7 倍），而文件层与内容层**全部通过** ——
因为所有环节用的是**同一个错数字**，内部完全自洽。

> **自洽 ≠ 正确。一致性检查发现不了「共同的错误前提」。**

### 4. 环节间数据契约

每环产出 `output.json`（供下游消费）+ `report.md`（给人看）+ `data.xlsx`（给表用）。
**下游只读上游的 output.json**，不靠人工搬运。

---

## 快速开始

```
你：帮我拆一下这个竞品 B0XXXXXXXX
AI：（加载本技能）声明计划 → 执行 → 遇闸门停下问 → 产出三件套
```

不需要记技能名或环节编号。首次使用建议先读 [`docs/getting-started.md`](docs/getting-started.md)。

---

## 安装

### 方式 A · 直接复制目录（最通用）

```bash
git clone <this-repo>.git
cp -r amazon-ops-orchestrator ~/.workbuddy/skills/     # WorkBuddy / CodeBuddy
# 或
cp -r amazon-ops-orchestrator ~/.claude/skills/        # Claude Code
```

### 方式 B · 通过 Skills CLI

```bash
npx skills add <owner>/<repo>@amazon-ops-orchestrator -g -y
```

### 方式 C · 解压分发包

下载 Release 中的 zip，解压到对应 agent 的 skills 目录即可。

---

## 配置

```bash
cp skill.config.example.json skill.config.json
# 编辑 skill.config.json
```

### 与 amazon-coach 集成（**本项目要求配置**）

本技能的费率、字符规范、政策口径均以 **amazon-coach** 知识库为权威来源
（20 张必需卡，含 `verifiedAt` / `volatile` / `reviewDueAt` 时效管理）。

**配置方式**（任选其一，优先级从高到低）：

```bash
# ① 环境变量
export AMAZON_COACH_DIR=/path/to/amazon-coach/data

# ② 配置文件
# skill.config.json -> "coach_dir": "/path/to/amazon-coach/data"
```

**未配置外部知识库时**，脚本会回退到技能自带的离线卡片集
`data/min-cards.json`（同样是那 20 张必需卡），**保证开箱即可运行**。

### 检查依赖状态

```bash
python scripts/_config.py      # 打印当前解析结果
python scripts/dep_check.py    # 检查卡片是否过期
```

⚠️ **卡片过期后必须联网复核官方口径再引用** —— 否则会静默使用旧费率
（与"币种读错"同性质：看不出来，但结论会错）。

---

## 目录结构

```
amazon-ops-orchestrator/
├── SKILL.md                    # 技能入口（agent 加载此文件）
├── README.md                   # 本文件
├── LICENSE                     # MIT
├── CHANGELOG.md                # 版本历史
├── skill.config.example.json   # 配置模板
├── docs/                       # 面向使用者的文档
│   ├── getting-started.md      #   起步指引
│   ├── roadmap.md              #   成熟度与改进路线
│   └── exporting.md            #   导出与跨 agent 安装
├── references/                 # 规则与规范（agent 按需加载）
│   ├── 00-flow-map.md          #   10 环依赖关系
│   ├── 01-gates.md             #   三级确认闸门
│   ├── 02-deliverable-spec.md  #   交付物格式
│   ├── 03-source-grading.md    #   来源分级与时效
│   ├── 04-data-source-ladder.md#   数据源三级降级
│   ├── 05-sop-index.md         #   后台操作 SOP 索引
│   └── 06-numeric-semantics.md #   数值语义规范
├── stages/                     # 10 个环节的定义
├── scripts/                    # 可执行脚本
├── assets/                     # 模板文件
├── data/                       # 自带的离线卡片集
└── tests/                      # 回归测试
```

---

## 脚本一览

| 脚本 | 作用 |
|---|---|
| `_config.py` | 统一配置解析（三级回退，解决路径硬编码） |
| `state.py` | 项目状态管理 CLI |
| `fetch_listing.py` | 抓取 listing 字段（强制存档原始页面） |
| `fetch_reviews.py` | 提取评论维度数据 |
| `fetch_suggestions.py` | 关键词扩展（搜索下拉建议） |
| `pricing_calc.py` | 利润测算与成本上限反推 |
| `listing_check.py` | 文案合规自检 |
| `make_xlsx.py` | 零依赖 xlsx 生成 |
| `selfcheck.py` / `crosscheck.py` / `semantic_check.py` / `report_check.py` | 四层自查 |
| `dep_check.py` | 外部依赖时效检查 |

---

## 设计原则

1. **宁可标注缺失，不要估算填充** —— 假数据比没有数据更糟
2. **区分「实测」与「假设」** —— 假设字段带 `is_assumption` 标记，下游引用时强制带标注
3. **校验器本身也要被校验** —— 本项目两个自查脚本首版各有数十项误报；
   误报泛滥会让检查被忽略，失去价值
4. **不替使用者决策** —— 高风险节点给方案让用户选，不自行定稿

---

## 已知边界

- **无工具账号时**：搜索量、竞争度、月销量等量化值拿不到，只能做相对分级
- **结构性缺失**：竞品退款率、平台执法尺度 —— 官方不公布，有账号也拿不到
- **需实盘验证**：文案转化效果、广告 ACoS 需上架后才能验证
- **无实物时**：包装尺寸靠假设，视觉只出拍摄简报不生成商品图

详见 [`docs/roadmap.md`](docs/roadmap.md)。

---

## 免责声明

本项目与 Amazon 无任何隶属或背书关系。文中的费率与政策信息以转述方式呈现并注明来源，
**使用前请以 Amazon 官方页面为准**。本项目产出仅供参考，不构成投资或经营建议。
详见 [`LICENSE`](LICENSE) 的附加说明。

---

## 贡献

欢迎提交 Issue 与 PR。改动环节定义或脚本后，请同步更新 `CHANGELOG.md`。

---

## 许可

[MIT](LICENSE)
