# SOP 索引：amazon-coach 落地动作清单

## 定位说明（重要）

`amazon-coach/data/sop.json` 里的 8 套 SOP 是**后台操作路径**，不是分析决策方法。

每步的结构是五段式：

| 字段 | 含义 |
|---|---|
| `where` | 后台位置（如 `顶部导航 Catalog → Add Products`） |
| `do` | 具体操作 |
| `why` | 为什么这么做 |
| `verify` | 怎么确认做对了 |
| `source` | 来源 |

**在流程里的角色**：流程走到"要落地了"的时候引用它，告诉用户在后台具体怎么点。**不用它来做分析决策**。

结构层级：`sops[] → branches[] → steps[]`，每套 SOP 含 `rootGoal` 和 `preconditions`。

## 8 套清单

| ID | 标题 | module | 对应环节 | 何时引用 |
|---|---|---|---|---|
| sop001 | 新商品上架（创建全新 Listing） | Listing | 06 / 08 | 文案定稿后，要实际上架时 |
| sop002 | 创建 FBA 货件（Send/Replenish Inventory） | FBA | 08 之后 | 商品上架后补货时 |
| sop003 | 创建 Sponsored Products 广告活动 | Advert | 09 | 广告架构定稿后，要建活动时 |
| sop004 | 创建 Coupon（优惠券） | Promo | 10 | 需要促销拉动时 |
| sop005 | 回复客户邮件（Buyer-Seller Messages） | CS | 03 / 10 | 处理买家消息时 |
| sop006 | 下载业务报告与广告报告 | Report | 03 / 10 | 需要真实数据做复盘时（P0：需登录后台） |
| sop007 | 查看账户健康（Account Health） | Rules | 08 | 合规体检时对照 |
| sop008 | POA（Plan of Action）申诉提交 | Rules | 08 / 10 | 账号出问题时的应急路径 |

## 引用方式

到落地阶段时，读 `data/sop.json` 取对应 SOP，输出成待办清单：

```markdown
## 落地动作清单（来自 sop001）

**前置条件**
- [ ] 已有 UPC/EAN（或 Brand Registry 用 GTIN 豁免）
- [ ] 类目未锁定
- [ ] 已决定 FBA 还是 FBM

**① 入口与类目**
1. 进入 Add Products
   - 位置：顶部导航 Catalog → Add Products
   - 操作：点击 Catalog，下拉中选 Add Products
   - 验证：页面跳到 Add a product，能看到搜索框
   - 来源：Seller Central Help - Add a product
...
```

## ⚠️ 已知局限（引用时必须告知用户）

1. **菜单路径需实测**：`sop.json` 的 `source` 字段自己声明——"详细到具体子菜单拼写建议上岗后打开真实后台再核对一遍（不同站点/权限/类目会略有差异）"。引用时要把这句带上。
2. **无真实账号时无法验证**：用户目前无 Seller Central 账号，这些路径是**资料整理的产物**，不是实测结果。在作品集里引用时要如实说明。
3. **SOP 不等于分析能力**：能照着 SOP 上架，不等于知道该上架什么、文案该怎么写。前者是操作，后者是本技能 `stages/` 负责的部分。

## 与 10 环的边界

```
10 环（本技能）          →  产出：该做什么、为什么、做成什么样
        ↓
SOP（amazon-coach）      →  产出：在后台怎么点、填哪个框、怎么确认
```

两边**不重叠**。写报告时不要用 SOP 的内容充当分析结论，也不要用分析结论替代操作步骤。
