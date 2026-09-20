# 环节 03 · 评论与 VOC 分析

**闸门**：🟢 P2（自动放行，做完汇报即可）
**目录**：`projects/<代号>/03-评论与VOC分析/`
**上游**：02 竞品拆解（需要目标 ASIN）
**下游**：04 关键词库（买家语言）、06 Listing 文案（痛点回应）、07 视觉素材（具象顾虑）

---

## 目标

回答一个问题：**买家到底在为什么买单，又到底在抱怨什么。**

输出两样可直接复用的东西：

1. **买家语言库** —— 买家自己的用词，可直接进文案与关键词（比卖家臆想的词更有效）
2. **痛点清单** —— 带严重度与可解决性排序

---

## 输入要求

| 输入 | 必需 | 缺失时 |
|---|---|---|
| 目标 ASIN | 是 | 从 02 环节的 output.json 读 |
| 评论内容 | 是 | 见下方「数据获取路径」 |
| 星级分布 | 是 | 02 环节已有，可直接复用 |

---

## 数据获取路径（关键，请按序尝试）

| 路径 | 条件 | 说明 |
|---|---|---|
| **L1** | 有第三方工具账号 | 直接拉取评论全文，最完整 |
| **L2-a** ⭐ | 无需账号 | **从 listing 页提取 Amazon 官方评论洞察模块** —— 主力路径 |
| L2-b | 无需账号 | 评论专页 `product-reviews` —— 需登录态，实测通常不可得 |
| L3 | 都拿不到 | 只有星级分布，分析降级为「分布解读 + 无正文」 |

### ⭐ L2-a 详解（本次实测打通）

Amazon 在 listing 页 HTML 内嵌了 **aspect 级评论分析数据**，以 `k+b64` 形式注释在 `k-injected` 块里。

- **定位**：搜 `k+b64` 得到一批 base64 块，逐个解码为 JSON，找 `k-component` 为 `AspectList-*` 的那个
- **数据位置**：`k-data.aspectsFlattened`（数组，通常 6–8 个维度）
- **每个维度字段**：

| 字段 | 含义 |
|---|---|
| `label` | 维度名（如 quality / delicacy / value for money） |
| `mentions` | 提及该维度的评论条数 |
| `mentionsPercentage` | 该维度占全部评论的比例 |
| `sentiment` | 整体情感倾向 |
| `sentimentMentions` | 其中**正面**提及条数 |
| `summary` | Amazon 生成的该维度摘要 |
| `snippets[]` | 原始评论片段（含碎片化文本 + review URL） |

**提取脚本**：`scripts/fetch_reviews.py`

⚠️ **可靠性警示**：
- 此结构依赖 Amazon 前端实现，**改版即失效**。每次运行后必须校验 `aspectsFlattened` 非空且字段完整
- 若解析失败，降级到 L3，**不要用旧数据或猜测填充**
- `snippets` 是 Amazon **精选**的片段，存在选择性偏差；判读时以「提及次数 + 情感计数」为主，片段为证

### 核心分析方法：找「高提及 + 低正面率」的维度

`mentions - sentimentMentions` = **非正面提及条数**。这是定位痛点最直接的信号：

```
正面率 = sentimentMentions / mentions

正面率 ≈ 100%  → 该维度是安全的加分项，可在文案中放心强调
正面率明显偏低  → 该维度是风险点，须在文案/产品端回应
```

**痛点不在「提及少的维度」，而在「提及多但正面率低的维度」** —— 后者才是买家在意却没被满足的地方。

---

## 执行步骤

### 第 1 步 · 建立维度全景

列出所有 aspect，按 `mentions` 降序排，计算正面率。识别三类：

- **强项**（高提及 + 高正面率）→ 文案该强调的
- **痛点**（高提及 + 低正面率）→ 必须回应的
- **弱信号**（低提及）→ 样本不足，不下结论

### 第 2 步 · 挖痛点证据

进到 `正面率偏低` 的维度的 `snippets`，逐条读原始评论片段：

- 痛点具体是什么（不是"质量差"，而是"卡扣到货即断"）
- 出现频次
- 是否属于能通过文案/图片缓解，还是产品端必须改

### 第 3 步 · 建买家语言库

从 snippets 里提炼**买家自己的用词**，分类：

| 类别 | 用途 |
|---|---|
| 价值描述词 | 进标题/五点（他们怎么夸的） |
| 场景词 | 进五点与 A+（他们在什么场景用） |
| 顾虑词 | 进否定词或 FAQ（他们担心什么） |
| 情感词 | 理解购买动机 |

⚠️ 只收买家原文用词，**不要自己造词**。这是"买家语言库"与"卖家臆想词"的区别。

### 第 4 步 · 交叉验证

把痛点与环节 02 的 `copy_strategy.uncovered_points` 对照：

- 两者都指向同一个点 → **确认的机会点**，优先级最高
- 只有评论提到 → 供应端问题，文案无法解决，需产品侧决策
- 只有 02 提到 → 可能只是文案缺口，未必是买家真痛点

---

## output.json 的 payload 契约

```json
{
  "asin": "",
  "data_path": "L2-a | L1 | L3",
  "sample_size": { "total_reviews": 0, "rated_5": 0, "rated_below_5": 0 },
  "aspects": [
    {
      "label": "quality",
      "mentions": 27,
      "mentions_pct": 96,
      "sentiment": "positive",
      "sentiment_mentions": 26,
      "positive_rate": 0.96,
      "summary": "Amazon 生成的该维度摘要原文",
      "evidence_snippets": ["原始片段"],
      "classification": "强项 | 痛点 | 弱信号"
    }
  ],
  "pain_points": [
    {
      "pain": "卡扣到货即断",
      "aspect": "delicacy",
      "frequency": "低（1 条明确证据）",
      "severity": "高",
      "fixable_by_copy": false,
      "fix_note": "属产品端问题，文案无法弥补；需供应链改善或调整卖点方向"
    }
  ],
  "buyer_language": {
    "value_words": [],
    "scenario_words": [],
    "concern_words": [],
    "emotion_words": []
  },
  "cross_check_with_stage02": [
    {
      "point": "",
      "confirmed_by_both": true,
      "action": ""
    }
  ],
  "verdict": {
    "strongest_asset": "",
    "biggest_risk": "",
    "confidence": "L1 | L2 | L3"
  }
}
```

---

## 产出物

| 文件 | 内容 |
|---|---|
| `output.json` | 上述 payload + 通用外壳 |
| `report.md` | 维度全景 → 痛点证据 → 语言库 → 交叉验证 |
| `data.xlsx` | 维度汇总表 + 买家语言库 |

---

## 挂接技能

| 技能 | 何时用 |
|---|---|
| `scripts/fetch_reviews.py` | **主力**，L2-a 路径 |
| `agent-browser` | 需要登录态时（若用户愿意登录） |
| `ecommerce-competitor-analyzer` | 其客户评论维度可作对照 |
| `xiyou-insight` | L1 有账号时 |

---

## 汇报模板（P2 结束后）

```
【03 评论与 VOC 分析完成】

数据路径：L2-a（提取 Amazon 官方评论洞察模块），7 个维度
样本：117 条评论，其中正面 100 条 / 非正面 17 条

维度全景（按提及量）：
1. quality      27 条 · 96% 正面  ← 最强资产
2. delicacy     20 条 · 75% 正面  ← ！风险点
3. versatility  12 条 · 100%
...

痛点（高提及 + 低正面率）：
1. <痛点> — <证据> — 可由文案缓解 / 需产品端改
2. ...

买家语言库：<N> 个词，分 4 类

产出：projects/<代号>/03-评论与VOC分析/

下一步：建议进入 04 关键词库（用买家语言建词），或 06 文案（回应痛点）。
```

---

## 已知局限

1. **snippets 是精选片段**，不是全部评论 → 频次判断只能是量级，不能精确计数
2. **非正面率低不等于该维度差** —— 可能是样本少，须看 `mentions` 基数
3. **Amazon 归纳的维度名是英文**，映射到中文语境的买家表达时存在语义损耗
4. **不含竞品对比** —— 本环节分析单一对象，横向对比需在环节 02 补多个 ASIN
