# 数据源三级降级规则

## 设计目标

解决一个具体矛盾：**用户现在要做求职作品集（无卖家账号），但将来接上真实店铺后希望同一套东西能直接升级使用。**

做法：**数据源只负责填充，交付物模板不变。**

今天用 L2 产出的一份竞品分析，将来接上真实店铺后是同一个模板、同一个字段结构——只是填充方式从"粘贴"变成"自动拉取"。所以作品集不是一次性产物，会随能力升级而变厚。

## 三级定义

| 级别 | 条件 | 行为 | 交付物差异 |
|---|---|---|---|
| **L1** | 检测到已授权的数据源（MCP 连接器 / 已装 skill） | 自动拉取，字段尽量填满 | 无差异，`missing_fields` 少 |
| **L2** | 无账号，但数据可从公开渠道获得 | 浏览器抓取，或引导用户粘贴 | 无结构差异，字段照样填 |
| **L3** | 完全拿不到 | **显式标注缺失**，改用降级分析方法 | 结构相同，该字段为 `null` + 标注 |

**核心保证**：三级的 `output.json` **结构完全一致**。差别只在字段值和 `missing_fields` 的内容。

## L1 检测清单

开工前检查环境是否有以下能力（按需检查，不强制安装）：

| 能力 | 对应技能 | 覆盖环节 |
|---|---|---|
| LinkFox 选品 | `linkfox-amazon-product-selection` | 01/02 |
| LinkFox 店铺 | `linkfox-amazon-store-operations` | 06/08（需 SP-API 授权） |
| LinkFox 广告 | `linkfox-amazon-ads` | 09/10 |
| 卖家精灵 | `linkfox-wb-sellersprite`、`sellersprite-rpa` | 01/02/04 |
| Sorftime | `linkfox-wb-sorftime` | 01/02 |
| 前台数据 | `linkfox-wb-amazon-front-data` | 02/03 |
| 西柚洞察 | `xiyou-insight` | 02/04/09/10 |
| openboost | `proboost-amazon-*` | 01/02/04 |
| 出海匠 | `chuhaijiang` | 02/03 |

**检测到即用，检测不到不报错**——直接降到 L2。

## L2 手段（按优先级）

1. **用户保存页面**（推荐，零依赖）：让用户在**自己已登录的浏览器**里打开目标页 → `Ctrl+S` 保存 HTML
   （或全选复制文本）→ 落到 `projects/<代号>/<环节>/raw/` → 由脚本解析。
   **这是需要登录态时最干净的路径**：不提取 cookie、不装额外软件、不触碰平台条款。
2. **浏览器抓取**：
   - **纯公开页面**：直接用 `fetch_listing.py` / `fetch_reviews.py`（Python 直连，最轻）
   - **需要登录态或 JS 渲染**：用 `agent-browser`。**✅ 可用配方（2026-09-20 实测打通）**：

     ```bash
     node <node.exe> <...>/agent-browser/bin/agent-browser.js \
       --profile "Profile 1" --headed \
       --args "--disable-blink-features=AutomationControlled" \
       batch --bail "open <url>" "wait 7000" "get url" "get html <selector>"
     ```

     - **`--profile "<名字>"`** 复用 Chrome 登录态（先跑 `agent-browser profiles` 查名字；
       本机为 `Default(用户1)` / `Profile 1(Leithry)`）。**前提：用户已在该 Chrome profile 登录目标站点。**
     - **`--headed` 不可省**：headless 会被 Amazon 直接判定为机器人，跳到 `edgex/guard/rx` 守卫页且**不再放行**；
       开可见窗口 + 关闭自动化标识后，守卫页会在数秒内自动跳转到真实页面。
     - `wait 7000` 用于等守卫页放行；过短会停在守卫页。
     - `get html` **必须带选择器**（如 `get html #cm_cr-review_list`）；
       要整页 HTML 用 `eval document.documentElement.outerHTML`。
     - ⚠️ **页面状态跨 Bash 调用会被重置** → 所有步骤必须压进**同一次** `batch`；
       交互式登录（弹窗让用户慢慢操作）不可行。
     - ⚠️ 评论页星级筛选已改为 JS 动态渲染，URL 参数 `filterByStar=*` **已失效**，暂时无法用参数取差评。
     - ⚠️ 不要用 Python `subprocess` 包装 agent-browser 的长任务 —— 实测会被 SIGTERM 终止。
       改用 bash 直接调用并将输出重定向到文件。
     - ⚠️ **`--profile` / `--headed` / `--args` 只在 daemon 首次启动时生效**，后续命令带这些参数会被
       **静默忽略**（提示 `daemon already running. Use 'agent-browser close' first`）。
       **换 profile 或改参数前必须先 `agent-browser close --all`**，否则会用旧会话，极难排查。
     - ⚠️ **卖家账户访问不了 amazon.com 的评论专页**（会跳 `/ap/signin`）。
       实测：企业买家账户可正常访问评论页；换成卖家账户后商品页/账户页正常但评论页被拒。
       卖家身份与买家身份在 Amazon 是分离的 —— **抓评论必须用买家账户的登录态**。

3. **用户粘贴**：引导用户把 listing 内容、词表、报告导出内容贴进来
4. **公开资料检索**：联网查官方文档、政策页、行业公开报告

⚠️ **不要尝试提取浏览器 cookie 复用登录态**（实测不可行且不建议）：
Edge `Default` 的 cookie 库被独占锁定（`CreateFileW` 连共享读都返回 `WinError 32`），
且本机缺 DPAPI/AES-GCM 解密库。详见用户级记忆《浏览器 cookie 读不出来》。

L2 的产物要标注清楚数据获取方式：`origin: "竞品 listing 页抓取"` / `origin: "用户浏览器保存页面"` 等。

## L3 处理规范

**禁止行为**：
- 用估算值、行业均值、记忆值填充
- 写"约为""大约"来掩盖没有数据源的事实
- 用别处的数据冒充（如用自家数据推断竞品）

**正确做法**：

```json
{
  "field": "monthly_search_volume",
  "level": "L3",
  "reason": "无数据源，且用户未提供词表",
  "degraded_to": "相对热度分级（A/B/C 三档，基于竞品 listing 覆盖度反推）",
  "note": "非绝对搜索量，不可用于精确容量计算"
}
```

并在 `report.md` 的**正文对应位置**再标一次，不能只写在末尾表格里。

## 常见 L3 场景与降级方案

| 缺失字段 | 常见原因 | 降级方案 |
|---|---|---|
| 月搜索量 | 无工具账号 | 改相对热度分级（竞品 listing 覆盖度反推） |
| 竞品销量 | 无工具账号 | 改用评论数增速 + BSR 区间做粗略量级判断，明确标注为量级非精确值 |
| 竞品广告投放数据 | 无工具账号 | 前台搜索页广告位观察 + Sponsored 标记统计 |
| 自家转化率 / ACoS | 无店铺 | 该环节整体降级为"方法论输出 + 模板"，不产出诊断结论 |
| 品类佣金率 | 可查官方费率表 | 通常能查到，不算 L3 |
| 竞品退款率 | **官方不公布** | 永久 L3，任何来源的竞品退款率都是推测 |

⚠️ 最后一条是**结构性缺失**，不是缺工具——即使有账号也拿不到。这类字段永远标 L3。

## 升级路径

用户将来接上真实店铺后的升级动作：

1. 授权 MCP 连接器 / 安装 B 类技能
2. 重跑受影响的环节（不必重跑全链）
3. `output.json` 结构不变，`missing_fields` 自动减少
4. 新旧版本的差异会被记录在项目档案里，**旧产出物保留**，方便对比"当时的判断 vs 有数据后的判断"

这个对比本身对求职作品集有价值——能展示"在数据受限条件下如何做出可辩护的判断"。
