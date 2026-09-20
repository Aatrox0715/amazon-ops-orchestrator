---
name: amazon-ops-orchestrator
version: 0.4.0
description: 亚马逊运营全流程总控台。当用户提出任何亚马逊运营任务时优先加载——包括市场调研、品类选品、竞品拆解、评论与 VOC 分析、关键词库搭建、定价与利润测算、Listing 标题/五点/描述编写、A+ 与视觉素材规划、Listing 合规体检、广告架构规划、广告与评论复盘、迭代优化。也适用于"我该从哪开始""帮我看看这个 ASIN""这个词库怎么搭""listing 怎么写""这周的广告怎么调"这类只说了目标、没说步骤的请求。触发词：亚马逊、Amazon、ASIN、listing、选品、竞品、关键词、词库、ACoS、TACoS、BSR、FBA、上架、主图、五点、A+、review、运营流程、电商运营。
agent_created: true
---

# 亚马逊运营总控台

> **版本 0.4.0** ｜ 变更历史见 `CHANGELOG.md` ｜ 成熟度与改进路线见 `docs/roadmap.md`

## 首次使用先读

- **`docs/getting-started.md`** —— 起步指引：任务类型、需要提供什么、交付物在哪、怎么自查
- **`docs/roadmap.md`** —— 成熟度评估：当前能力边界与已知不足
- **`README.md`** —— 项目说明与安装方式

## 定位

这个技能**不是亚马逊知识库**，是**流程调度器**。

它做四件事：
1. 听懂你要什么，判断该走哪一环
2. 按环节定义把活干了，产出结构化交付物
3. 在应该停下的时候停下，等你拍板
4. 把成果落盘成档案，下一步能直接接上

它**不做**的事：不替你决策，不编造数据，不跳过确认闸门。

---

## 启动协议（每次对话开始必做）

**第 1 步 · 找项目**

检查 `E:\workbudyy\amazon-ops\projects\` 下有哪些项目目录。

- **有活跃项目** → 读该项目 `_state.json`，恢复上下文：走到哪一环了、哪些决策已确认、当前数据源级别
- **无项目** → 问用户："这是新项目吗？给个产品代号。"然后 `python scripts/state.py new <代号>`
- **不确定做哪个** → 列出所有项目及各自进度，让用户选

**第 2 步 · 定意图**

对照下方「环节路由表」，确定用户当前要哪一环。

- 用户只说了目标没说环节（如"帮我看看这个 ASIN"）→ 由你判断，**并说明你判断成了哪一环、为什么**
- 用户一次说了多个环节 → 按依赖顺序排，告诉用户"先做 A，A 定稿后接着做 B"
- 用户说的不属于 10 环（如"帮我写周报"）→ 说明这不在流程内，问是否仍要处理

**第 3 步 · 声明计划**（必做，不能省）

开工前用三行说清楚：
- 这次做哪一环、要什么输入
- 产出什么（文件名 + 格式）
- 在哪一步会停下来问你

**第 4 步 · 检查输入就绪度**

读该环节定义的「输入要求」，逐项核对。缺失的按 `references/04-data-source-ladder.md` 判级：
- L1 有数据源 → 自动拉
- L2 能抓取/你能粘贴 → 走降级路径
- L3 拿不到 → **明确标注，继续用降级模式跑，不许静默编造**

**第 5 步 · 执行并落盘**

按 `stages/stage-XX-*.md` 执行，写三件套，更新 `_state.json`。

---

## 环节路由表

| 用户可能这么说 | 环节 | 编号 |
|---|---|---|
| "这个类目能做吗""市场多大""选品" | 类目与市场调研 | 01 |
| "拆这个竞品""这个 ASIN 怎么样""对手怎么打的" | 竞品拆解 | 02 |
| "买家在骂什么""评论怎么样""痛点在哪" | 评论与 VOC 分析 | 03 |
| "词库怎么搭""要投哪些词""否定词" | 关键词库搭建 | 04 |
| "定价多少合适""能赚多少""FBA 费用" | 定价与利润测算 | 05 |
| "写 listing""标题""五点""描述" | Listing 文案编写 | 06 |
| "主图怎么规划""A+ 怎么做""视觉" | 视觉素材规划 | 07 |
| "查一下合规""有没有违规""体检" | 合规与质量体检 | 08 |
| "广告怎么搭""开什么活动""预算怎么分" | 广告架构规划 | 09 |
| "广告效果怎么样""ACoS 太高""怎么优化" | 复盘与迭代 | 10 |

完整依赖关系见 `references/00-flow-map.md`。

---

## 三条铁律

### 铁律一：不编造

任何拿不到的字段，**写 `null` + 标注 `L3` + 说明缺什么**，绝不用估算值、行业惯例值、记忆值填充。

在报告里显式呈现为：

```
搜索量：L3 缺失（无数据源，且未提供词表）
→ 本节改用竞品 listing 反推的相对热度分级，非绝对搜索量
```

**区分三种东西**：官方公布的事实 / 第三方工具数据 / 你的推断。三者标注方式不同，不能混为一谈。

### 铁律二：来源必标

每个事实性数字、每条政策口径，必须带来源和核实日期。分级规则见 `references/03-source-grading.md`。

最低要求格式：`值 · 来源 · 核实 YYYY-MM`

长期沿用的资产：**直接复用 `amazon-coach` 的 `sourceLabel` 与 `verifiedAt` / `volatile` / `reviewDueAt` 机制**，不要另造一套。事实类卡片（如标题字符限制、费率）在引用前先检查是否已过复核期：

- `volatile = true`（含金额/费率/政策日期）→ 6 个月复核一次
- `volatile = false`（稳定知识）→ 18 个月复核一次

已过期的事实**必须先联网核实再引用**，不能直接用旧值。

### 铁律三：闸门不可跳

三级闸门规则见 `references/01-gates.md`。核心：

| 级别 | 判据 | 行为 |
|---|---|---|
| 🔴 P0 | 不可逆 / 对外可见 / 花钱 | 必须停下等你明确批准，**不得自行推进** |
| 🟡 P1 | 高影响但可回滚 | 停下来给方案，等你选定后再往下 |
| 🟢 P2 | 可随时重做 | 自动做完，汇报结果即可 |

**跳过闸门比做错更严重**——做错能改，越权不能。

---

## 交付物规范

每完成一环，落盘三件套到 `projects/<代号>/<环节目录>/`：

| 文件 | 给谁用 | 强制 |
|---|---|---|
| `output.json` | 下游环节消费（唯一数据通道） | 是 |
| `report.md` | 给人看，含来源标注与 L3 缺口 | 是 |
| `data.xlsx` | 给表格用（仅数据密集型环节） | 视环节而定 |

规范细节见 `references/02-deliverable-spec.md`。

**关键原则**：环节之间**只通过 `output.json` 传递数据**，不靠用户搬运。上游写进 output.json，下游从 output.json 读。这才叫"跑通流程"。

---

## 目录索引

```
SKILL.md                     ← 本文件（技能入口）
README.md / LICENSE / CHANGELOG.md
skill.config.example.json    ← 配置模板（复制为 skill.config.json）
docs/                        ← 面向使用者的文档
  getting-started.md            起步指引
  roadmap.md                    成熟度与改进路线
  exporting.md                  导出与跨 agent 安装
references/                  ← 规则与规范（按需加载）
  00-flow-map.md              10 环依赖关系与全流程图
  01-gates.md                 三级确认闸门规则
  02-deliverable-spec.md      交付物格式规范
  03-source-grading.md        来源分级与时效机制
  04-data-source-ladder.md    数据源三级降级规则
  05-sop-index.md             后台操作 SOP 索引
  06-numeric-semantics.md     数值语义规范（币种/单位/量纲/假设）
stages/                      ← 10 个环节定义
  stage-01-market.md          类目与市场调研
  stage-02-competitor.md      竞品拆解
  stage-03-voc.md             评论与 VOC 分析
  stage-04-keyword.md         关键词库搭建
  stage-05-pricing.md         定价与利润测算
  stage-06-listing.md         Listing 文案编写
  stage-07-visual.md          视觉素材规划
  stage-08-compliance.md      合规与质量体检
  stage-09-ads.md             广告架构规划
  stage-10-review.md          复盘与迭代
assets/                      ← 模板
  _state.template.json        项目状态模板
  output.template.json        output.json 契约模板
data/                        ← 自带离线卡片集（未配外部知识库时使用）
  min-cards.json              20 张必需卡（费率/规范口径）
scripts/                     ← 脚本（见下）
tests/                       ← 回归测试
projects/                    ← 项目产出物（.gitignore 已忽略）
```

### 路径解析（三级回退）

所有脚本通过 `scripts/_config.py` 解析路径，**不再硬编码**：

```
1. 命令行参数
2. 环境变量 AMAZON_OPS_ROOT / AMAZON_COACH_DIR
3. <技能目录>/skill.config.json
4. 兜底：<技能目录>/projects 与 <技能目录>/data
```

先跑 `python scripts/_config.py` 查看当前解析结果。

### ⚠️ 四层自查都要跑，缺一不可

| 层 | 脚本 | 验什么 | 缺了会怎样 |
|---|---|---|---|
| 文件层 | `selfcheck.py` | 文件在不在、契约全不全 | 交付不完整 |
| 内容层 | `crosscheck.py` | 跨环节一致、引用链完整、观察是否闭环 | 环节间脱节 |
| **基数层** | `semantic_check.py` | **币种 / 单位 / 量纲 / 假设标注** | **共同错误前提无法发现** |
| 报数层 | `report_check.py` | 报告是否残留作废值 | 报告与数据不一致 |

> **实测教训（这是本技能最重要的设计依据）**：
> 曾发生售价币种读错（把 `CNY 66.88` 当 `$66.88`），造成售价放大 6.7 倍、污染下游两个环节。
> 当时文件层与内容层**全部通过** —— 因为所有环节用的是**同一个错数字**，内部完全自洽。
>
> **自洽 ≠ 正确。** 一致性检查发现不了「共同的错误前提」，
> 所以**基数级校验（币种/单位/量纲）必须单独设关卡**。
>
> 另注：`report_check` 与 `semantic_check` 的首版**自己也有误报**
> （前者把 `$20.12` 抓成 `20` 再命中 `2026`；后者连"标题字符数"都要求写单位）。
> **校验器本身也需要被校验** —— 误报泛滥会让检查被忽略、失去价值。

## 脚本用法速查

```bash
cd C:\Users\10306\.workbuddy\skills\amazon-ops-orchestrator\scripts

# 项目状态
python state.py new <代号> --name "产品名"
python state.py show <代号>
python state.py stage <代号> <环节号> <状态> --output <路径>
python state.py missing <代号> add "字段" "原因" "降级方式"

# 抓取 listing（L2 手段）
python fetch_listing.py <ASIN> --project <代号> --market US --stage 02
python fetch_listing.py <ASIN> --project <代号> --stage 02 --reparse   # 改了解析规则时复用已存 raw

# 提取评论洞察（L2-a 手段，复用 fetch_listing 存下的 raw，无需登录）
python fetch_reviews.py <ASIN> --project <代号>

# 生成 xlsx
python make_xlsx.py <输出路径> --data <数据json>
```

⚠️ **抓取后必须校验解析结果**：`fetch_listing.py` 的正则依赖页面结构，Amazon 改版会导致字段静默抓错。
**关键数字要做内部一致性校验**（如星级分布加总应为 100%、加权均分应等于展示分）。
一旦发现矛盾，先诊断 raw HTML 再落笔 —— **错误的数字比没有数字更糟**。

---

## 外部资产引用

| 资产 | 路径 | 在流程里的角色 |
|---|---|---|
| FBA Coach 知识库 | `C:\Users\10306\WorkBuddy\2026-09-06-17-10-09\amazon-coach\` | 事实底座 + 落地动作清单 |
| ├ `data/flashcards.json` | 141 张卡，含 sourceLabel / verifiedAt | **事实与口径的权威来源**，引用前查时效 |
| ├ `data/sop.json` | 8 套后台操作 SOP | **执行落地**：决策做完后告诉用户怎么在后台操作 |
| ├ `data/map.json` | M1–M7 知识地图 | 流程与知识模块的对照参照 |
| └ `data/bank.json` | 34 道面试题 | 方法论解释（解释"为什么这么干"时可用） |

⚠️ **注意 SOP 的真实定位**：`sop.json` 是**后台操作路径**（点哪里、填什么、怎么验证），不是分析决策方法。分析框架需按 `stages/` 里的定义执行，SOP 只在流程末尾作为"落地动作清单"引用。

---

## 现成技能挂接

各环节可调用市场上的现成技能做增强。**挂接时不硬依赖**——技能不存在或不可用时，按环节定义内置逻辑降级执行。

| 环节 | 可挂接技能 | 类型 |
|---|---|---|
| 01 市场调研 | `amazon-category-selection-analysis` | A 零依赖 |
| 02 竞品拆解 | `ecommerce-competitor-analyzer` | A 零依赖 |
| 04 关键词库 | `amazon-keyword-strategy` | A 零依赖 |
| 05 定价利润 | `amazon-profit-calculator` | A 零依赖 |
| 06 Listing 文案 | `amazon-listing-generator`、`cross-border-listing` | A 零依赖 |
| 07 视觉素材 | `listing-images`、`ecommerce-listing-image-set` | A 零依赖 |
| 08 合规体检 | `amazon-listing-doctor`、`amazon-listing-alexa-optimizer` | A 零依赖 |
| 09/10 广告 | `xiyou-insight`、`linkfox-amazon-ads` | B 需账号 |

A 类 = 无需账号，粘贴/抓取即可跑。B 类 = 需数据源授权，**有账号时自动启用，无账号时按 L3 降级**。
