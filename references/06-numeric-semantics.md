# 数值语义规范（基数级校验的基础）

> 建立原因：2026-09-20 实战中发生「售价币种读错」——页面显示 `CNY 66.88`，被当成 `$66.88` 使用，
> 放大 6.7 倍并污染下游两个环节。**21 项跨环节一致性检查全部通过，因为所有环节用的是同一个错数字。**
>
> **教训：自洽 ≠ 正确。** 一致性检查发现不了「共同的错误前提」。
> 本规范用于把「数值的语义」显式化，让校验能落到基数层面。

---

## 一、核心原则

**任何数值字段都必须能回答三个问题：**

| 问题 | 对应元数据 | 不回答的后果 |
|---|---|---|
| 它的**单位 / 币种**是什么？ | `unit` / `currency` | 币种错 → 数值放大数倍（已实际发生） |
| 它的**量纲**是什么？ | `dimension` | 重量当尺寸、百分比当绝对额 |
| 它**从哪来、什么口径**？ | `source` / `basis` | 无法判断是否可比 |

**四类必须标注元数据的字段**：

```
金额类 → currency（USD/CNY/…）
度量类 → unit（g / cm / in / cu_ft / …）
比率类 → scale（percent / ratio / basis_point）
计数类 → unit（piece / order / review / …）
```

---

## 二、字段元数据格式

在 `output.json` 中，数值字段应写成**带元数据的对象**，或与元数据并置：

### 推荐写法（对象形式）

```json
{
  "sell_price": {
    "value": 9.99,
    "currency": "USD",
    "unit": "per_unit",
    "source": "Amazon 前台 listing 页（强制 i18n-prefs=USD）",
    "verified_at": "2026-09",
    "evidence": "02-竞品拆解/raw/price_verified.json"
  }
}
```

### 兼容写法（标量 + 旁置元数据）

存量数据多为标量，允许保留，但**必须在同一 payload 层级提供对应元数据**：

```json
{
  "sell_price": 9.99,
  "currency": "USD",
  "price_source": "Amazon 前台 listing 页",
  "price_evidence": "raw/price_verified.json"
}
```

**校验规则**：`crosscheck.py` 会检查 —— 凡是命中「金额类字段名模式」的标量，**同级必须存在 `currency`**；否则判 fail。

---

## 三、字段名模式 → 元数据类型映射

校验器按字段名识别类型。**新增字段时若不符合下表的模式，需补进本表**。

| 类型 | 字段名模式（正则） | 必需元数据 |
|---|---|---|
| 金额 | `price\|cost\|fee\|revenue\|profit\|sales\|amount\|budget\|bid\|acos\|tacos` | `currency` |
| 度量 | `weight\|size\|dimension\|length\|width\|height\|volume\|cbm` | `unit` |
| 比率 | `rate\|ratio\|pct\|percentage\|share\|margin` | `scale`（percent/ratio） |
| 计数 | `count\|qty\|quantity\|number\|total_reviews\|units` | `unit` |

⚠️ **例外**：字段名同时含金额与比率时（如 `acos`、`margin`），按**比率**处理（比率本身无需币种，但若以金额计算，须在 `basis` 里说明）。
⚠️ **本体（entity）不参与校验**：如 `paid_amount` 是金额 ✓，但 `amount_of_reviews` 是计数 —— 校验器按最长匹配优先，并在报告中列出**无法归类的字段**供人工确认。

---

## 四、假设字段的标注（配合假设追踪机制）

**凡是由推断而非实测得到的值，必须显式标注为假设**：

```json
{
  "size_tier": {
    "value": "large_standard",
    "is_assumption": true,
    "assumption_basis": "手链含礼盒，短边通常 >1.9cm（无实物，未实测）",
    "impact": "影响 FBA 配送费 $0.62/件",
    "how_to_verify": "量取包装短边是否 ≤1.9cm"
  }
}
```

**规则**：

1. `is_assumption: true` 的字段，**下游引用时必须带标注**，不得直接当事实用
2. 假设必须写明 `impact`（影响什么、影响多少）与 `how_to_verify`（怎么验证）
3. `crosscheck.py` 会扫描所有 `is_assumption` 字段，检查下游是否在其报告中标注

---

## 五、常见错误模式（来自实战）

| # | 错误 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | **币种读错** —— 页面按来源地本地化显示，抓取只取数字 | 售价放大 6.7 倍（已实际发生） | 抓取时强制目标币种；提取必须「符号 + 金额」同现 |
| 2 | **单位混用** —— 英寸/厘米、克/盎司 混用 | FBA 分段判错，费用差数倍 | 元数据写 `unit`，并在报告里标注换算 |
| 3 | **比率当绝对额** —— 把 20% 写成 $20 | 费用高估 | 比率类写 `scale`，不写 `currency` |
| 4 | **口径混用** —— 竞品退款率（官方不公布）与自家退款率混用 | 结论不可比 | `source` 必须区分「自家实测」与「第三方/经验」 |
| 5 | **假设当事实** —— 假设的尺寸分段被下游当实测值引用 | 费用测算失准 | 加 `is_assumption` 标注 |

---

## 六、校验器行为

`crosscheck.py` 的「基数级校验」按本规范执行：

1. **扫描** output.json 中所有数值字段
2. **归类**（按第三节的模式表）
3. **检查元数据是否齐备**（金额要有 currency、度量要有 unit …）
4. **跨环节比对**：同一语义字段在不同环节的值必须一致，且**币种/单位必须相同**
5. **扫描假设字段**：`is_assumption: true` 的字段，检查下游是否标注
6. **列出无法归类的字段**供人工确认

**判定**：
- 元数据缺失 → ❌ fail
- 元数据冲突（如 02 是 USD、05 是 CNY）→ ❌ fail
- 存在无法归类的数字字段 → ⚠️ warn
- 全部通过 → ✅ pass
