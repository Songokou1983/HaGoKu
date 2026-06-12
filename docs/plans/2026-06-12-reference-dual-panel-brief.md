# 参考双面板 redesign brief v1（2026-06-12）

> **交付模式**：**一个 PR、一次做完**（可与其它工作并行，但本 brief 自洽可独立合）。
>
> **读者**：实施开发（AI 或人）。按 **CO-R01～CO-R10** 勾选，全部完成后再提 PR。
>
> **前置**：
> - Web UI 一次性交付（[`2026-06-11-web-ui-ab-brief.md`](2026-06-11-web-ui-ab-brief.md)）已合或同分支可用：`focusAreas.ts`、Analyze `InputBar`、`KnowledgePanel` 骨架。
> - 工具箱增强（[`2026-06-11-toolbox-enhancement-brief.md`](2026-06-11-toolbox-enhancement-brief.md)）已合：`memory/methods/` ≥12 篇 + `/api/kb` frontmatter 解析。
>
> **触及范围**：`hagoku_web/` 为主 + 同步修订 `docs/COMMAND_SYSTEM.md`；**不**扩展 `command_parser.py` 命令种类（铁律 1）。

---

## §0 交付后用户应感受到什么

| 角色 | 一句话 |
|------|--------|
| **分析师用户** | 侧栏两个入口分工清楚：**知识库**查方法，**对话指引**查怎么跟分析师说话；分析暂停时不用切来切去猜语法 |
| **维护者** | UI 教的斜杠命令与 `command_parser.py` **完全一致**；改命令只动 `commandsRegistry.ts` 一处 |

**设计核心（不可妥协）**：**用户真正可用** —— 在字段表/清洗/统计暂停点，80% 场景**直接说话**即可；斜杠命令是可选加速器；**没有假命令**（`/confirm`、`/how` 不得再作为斜杠语法教学）。

**IA 决策（已确认）**：**保持两个侧栏项**，不合并 Tab：
- **知识库** — 方法是什么（读）
- **对话指引** — 现在怎么说、点什么（做）

二者**并列 + 互链**，不是一个大杂烩面板。

---

## §1 现状问题（开发前先读）

### 1.1 后端真实命令（SSoT）

**文件**：`hagoku/manager/command_parser.py`

| 命令 | 权威语法 | 作用 |
|------|----------|------|
| `/goal` | `/goal <自然语言>` | 补充/修正分析目的 → `context._user_goal_update` |
| `/rename` | `/rename 列A=中文名, 列B=中文名` | 字段显示名 → `context._user_column_renames` |
| `/use` | `/use 列1, 列2, ...` | 限定参与分析列 → `context._user_specified_columns` |

**不是命令**（不以 `/` 结构化解析）：自然语言、`/confirm`、`/how` 及一切其它 `/xxx`。

**路由**：`pipeline_helpers._handle_command_if_present` — 命令内容注入 context，由当前关注点 LLM 理解执行。

### 1.2 前端与文档错位（必须修）

| 问题 | 用户后果 | 位置 |
|------|----------|------|
| UI 教 `/rename A → B` | 复制后 parser 不认 `=` 对 | `CommandsPanel.tsx` |
| UI 教 `/confirm` | 用户以为有魔法命令 | `CommandsPanel.tsx` |
| UI 教 `/how` | 与知识库、`query_method` 重复 | `CommandsPanel.tsx` |
| 速查 + 分阶段 **重复两遍** | 信息噪音、信哪份 | `CommandsPanel.tsx` |
| 知识库 category 无中文映射 | `statistics` 裸显 | `KnowledgePanel.tsx` |
| KB 空列表 | 「做了等于没做」 | API 未重启 / `/api/kb` 失败时空态无指引 |
| `COMMAND_SYSTEM.md` 过时 | 仍写四 Agent、未写对话指引分工 | `docs/COMMAND_SYSTEM.md` |

### 1.3 与知识库 / 工具箱边界

| 层 | 职责 | Web 入口 | 运行时 |
|----|------|----------|--------|
| 方法库 `memory/methods/` | Why / Which method | **知识库** | LLM `query_method` / `read_method` |
| 斜杠命令（3 个） | 结构化沟通意图 | **对话指引** + InputBar | `command_parser` |
| UI 按钮 | 流程放行 | **分析页** | WS `respond` + LLM `route_to` |
| agent_tools（~44） | 计算执行 | 不在用户输入层暴露 | function calling |

**禁止**：为每个 tool 增加斜杠命令；在对话指引里写长篇统计教程。

---

## §2 设计锚点（不可推翻）

1. **Industrial Data Terminal**：与 Web UI brief 一致；Lucide 图标；无 emoji 按钮。
2. **四关注点叙事**：用户可见文案用 `focusLabel()`；协议 key 仍为 scout/cleaner/analyst/reporter。
3. **可用性优先**：分析页 InputBar 是对话主战场；指引面板必须能 **复制/填入** 示例。
4. **SSoT**：命令定义 → `commandsRegistry.ts`（Panel + InputBar + 测试共用）；方法条目 → `/api/kb`（不变）。
5. **铁律 1**：不为 `rename` 的 `→` 增加 parser 分支；**改 UI 跟 `=` 走**。
6. **铁律 10**：若改 `prompt.md` 中与命令相关的段落 → PR 附 dump 对比；本 brief **默认不改 prompt**（除非发现与 registry 冲突）。

---

## §3 信息架构

### 3.1 侧栏（保持 2 项，不改组名）

**文件**：`hagoku_web/src/App.tsx`

```
参考
├── 知识库          id: knowledge   （不变）
└── 对话指引        id: commands    title 改文案，路由 id 可保留 commands 免动 store）
```

**改名**：

| 现 | 新 |
|----|-----|
| 命令指引 | **对话指引** |
| 命令速查表 | **跟分析师说话**（PanelHeader 副标题） |

### 3.2 互链（不合并组件）

| 从 | 到 | 文案 |
|----|-----|------|
| 知识库顶 | 切到对话指引 | 「跟分析师怎么沟通 → 对话指引」 |
| 对话指引顶 | 切到知识库 | 「统计/业务方法说明 → 知识库」 |
| Playbook 块底 | 知识库详情 | 「相关方法：ttest.md」等（`setActiveView` + 可选 deep link state） |

实现：`useWorkspaceStore.setActiveView('commands' | 'knowledge')`；deep link 可用 store 扩展 `kbOpenFilename?: string`（CO-R07，可选）。

---

## §4 交付清单 CO-R01～CO-R10

### A. 数据层

| ID | 内容 | 文件 |
|----|------|------|
| CO-R01 | 新建 `commandsRegistry.ts`：3 命令完整 metadata（syntax、examples、stages、kbLinks） | `hagoku_web/src/constants/commandsRegistry.ts` |
| CO-R02 | `CommandsPanel` 删除 `FAST_COMMANDS` / `STAGE_REF_COMMANDS` 硬编码重复；改读 registry + playbook 模板 | `hagoku_web/src/panels/CommandsPanel.tsx` |

**`CommandDefinition` 形状（示意）**：

```ts
export interface CommandDefinition {
  id: "goal" | "rename" | "use";
  slash: string;           // "/goal"
  label: string;           // 用户可见短名
  syntax: string;          // 与 command_parser 一致
  description: string;
  examples: string[];      // 可复制整行
  stages: StageKey[];      // 可用关注点
  kbLinks?: { filename: string; label: string }[];
}
```

### B. 对话指引面板重做（CO-R03）

| ID | 内容 |
|----|------|
| CO-R03 | 按 §5 结构重写 `CommandsPanel`（或拆 `InteractionGuidePanel.tsx` 再 re-export，二选一） |

**必须删除的用户可见内容**：
- `/confirm` 作为斜杠命令
- `/how` 作为斜杠命令
- 所有 `/rename ... → ...` 语法示例

**必须新增**：
- §0 三句话（对话 / 无 confirm / 方法去知识库）
- §1 三张快捷写法卡（registry 驱动）
- §2 四关注点 playbook（统一模板，不重复展开命令卡）
- §3 意图对照表（自然语言 vs 快捷命令）
- §4 FAQ（4 条，见 §5.4）

### C. 知识库面板增强（CO-R04）

| ID | 内容 |
|----|------|
| CO-R04 | `KnowledgePanel`：category 中文映射；搜索框（title/summary/tags 前端 filter）；空态区分 API 空 vs 连接失败 |

**Category 映射**：

| frontmatter `category` | UI |
|------------------------|-----|
| statistics | 统计学 |
| business | 业务分析 |
| cleaning | 数据清洗 |
| visualization | 可视化 |

**空态 copy（API 200 且 entries=[]）**：

> 暂无方法条目。若刚更新过代码，请重启 `hagoku-api` 后点重试。

### D. 分析页联动（CO-R05～CO-R07）

| ID | 内容 | 优先级 |
|----|------|--------|
| CO-R05 | `InputBar`：输入 `/` 弹出补全（仅 goal/rename/use）+ 选中后预填 + rename hint | P0 |
| CO-R06 | 对话指引「复制 / 填入输入框」：waiting 时写 `replyText`；否则 clipboard + toast | P1 |
| CO-R07 | 双面板互链按钮；`AnalyzePanel` InputBar `footerHint` 按 `waitingAgent` 上下文（registry 驱动） | P1 |

**InputBar 补全规则**：
- 仅当 value 以 `/` 开头且尚未空格时显示菜单
- 不包含 confirm / how
- IME composing 时不拦截 Enter（沿用现有 InputBar 逻辑）

### E. 知识库详情增强（CO-R09）

| ID | 内容 |
|----|------|
| CO-R09 | 详情页 footer 展示 frontmatter `tools` chip（只读说明：「分析师会通过工具执行」）；链到对话指引说明无需用户输入 tool 名 |

### F. 文档与测试（CO-R08、CO-R10）

| ID | 内容 |
|----|------|
| CO-R08 | 重写 `docs/COMMAND_SYSTEM.md`：3 命令、`= ` 语法、流程按钮不放命令、与知识库分工、指向本 brief |
| CO-R10 | 测试：`commandsRegistry.test.ts`（syntax 含 `=`、无 `→` 作语法）；`CommandsPanel.test.tsx` smoke（无 confirm/how 文案）；可选 `KnowledgePanel` category 映射 |

---

## §5 对话指引内容规格（CO-R03 验收文案）

### 5.1 §0 固定三句话

1. 你在和**一位数据分析师**对话；可以直接说话。
2. **`/goal` `/rename` `/use` 是可选快捷写法**，不是程序指令；内容仍由 LLM 理解。
3. **放行当前步骤**请用分析页按钮或说「确认继续」——**没有 `/confirm`**。方法背景见侧栏**知识库**。

### 5.2 §1 快捷写法（registry 三张卡）

每张卡字段：语法 · 说明 · 2 示例 · `[填入输入框]` · 可用关注点 chips

**`/rename` 权威示例（必须出现在 UI）**：

```
/rename Period=周次, inc1=店铺收入
```

### 5.3 §2 关注点 Playbook（四块，统一模板）

| 块 | focusLabel | 你会看到 | 可以说（NL 示例） | 可选快捷 | 怎么继续 | KB 链接 |
|----|------------|----------|------------------|----------|----------|---------|
| scout | 理解字段 | 字段核对表 | 「inc1 是店铺收入」 | rename, use, goal | **进入下一阶段** 按钮 | — |
| cleaner | 评估清洗 | 清洗评估/核对表 | 「空值用均值填，别删行」 | goal | **确认继续** 按钮 | outliers.md, missing-data.md |
| analyst | 跑统计 | 统计表 + 对话 | 「再对比一下分组收入」 | goal | **确认继续** / 同意进报告 | ttest.md, power-analysis.md |
| reporter | 写报告 | 报告链接 | 「结论再强调局限性」 | goal | **查看报告** | — |

Playbook **不得**再嵌套一整份命令速查列表。

### 5.4 §3 意图对照表

| 你想… | 直接说 | 快捷（可选） | 查方法 |
|--------|--------|--------------|--------|
| 改分析目的 | 「我想比各地区转化率」 | `/goal …` | 知识库 |
| 改字段中文名 | 「inc1 叫店铺收入」 | `/rename inc1=店铺收入` | — |
| 只要这几列 | 「只用收入和日期」 | `/use 收入, 日期` | — |
| 问 t 检验怎么用 | 输入框直接问 | — | ttest.md |
| 继续下一步 | 「确认继续」或点按钮 | **无 /confirm** | — |

### 5.5 §4 FAQ（4 条）

1. **命令会硬编码执行吗？** 不会；是给 LLM 的结构化说明。
2. **和直接说话区别？** 无本质区别；命令只是固定格式。
3. **一条消息多个命令？** 可以，建议一条一个意图。
4. **分析师用的工具我要输入吗？** 不用；你说需求，LLM 自己调工具；方法背景在知识库。

---

## §6 知识库面板规格（CO-R04、CO-R09）

### 6.1 列表页

- PanelHeader：**知识库** · 副标题「学术与业务分析方法」
- 互链：→ 对话指引
- 分类 chip + 搜索
- 卡片：title、summary、tags、category badge

### 6.2 详情页

- 现有 HTML 正文
- Footer：`tools: [...]` chips + 一句说明
- 返回列表保留 scroll 位置（现有行为保持）

### 6.3 与 `/api/kb` 契约

沿用 `server.py` `_kb_load_registry_entries` 返回：

```json
{ "entries": [{ "filename", "title", "summary", "category", "tags", "tools" }] }
```

**不新增**后端 API（除非 CO-R05 补全极复杂；默认前端 registry 静态）。

---

## §7 明确不做

| 项 | 原因 |
|----|------|
| 合并知识库 + 对话指引为一个 Tab | 用户已确认保持 2 入口 |
| 新增 `/confirm` `/how` parser | 违背 COMMAND_SYSTEM 原则 |
| `rename` 支持 `→` 语法分支 | 铁律 1；改 UI |
| 44 tools → 44 斜杠命令 | Phase D LLM 选工具 |
| 对话指引内嵌长篇方法正文 | 重复知识库 |
| lessons / 项目记忆进知识库面板 | 另 brief |
| 全文改 prompt.md | 非必须；冲突时最小改 + dump |

---

## §8 一次性验收

### 8.1 自动化

- [ ] `cd hagoku_web && npm test` 绿（含 CO-R10 新增）
- [ ] `pytest` 全绿（无后端行为变更时不应红）

### 8.2 用户任务（手工 15 分钟）

1. 字段表阶段：自然语言改字段名 → 表更新
2. 从对话指引复制 `/rename col=中文` → 发送 → **parser 生效**（非纯聊天）
3. 无任何 UI 教 `/confirm`；用户点 **确认继续** 进入下一阶段
4. 知识库 ≥12 条；分类 chip 中文；点开 ttest 正文
5. 跑统计 playbook 链到 power-analysis.md
6. 分析页输入 `/` 仅 3 项补全
7. waiting 时「填入输入框」可用

### 8.3 文档

- [ ] `COMMAND_SYSTEM.md` 与 registry / parser 一致
- [ ] PR body 说明双面板分工

---

## §9 文件清单

```
hagoku_web/src/
├── constants/
│   └── commandsRegistry.ts              # 新建 CO-R01
├── components/
│   └── InputBar.tsx                     # CO-R05 补全 UI
├── panels/
│   ├── CommandsPanel.tsx                # 重写 CO-R02/R03（或 InteractionGuidePanel.tsx）
│   ├── KnowledgePanel.tsx               # CO-R04/R09
│   └── AnalyzePanel.tsx                 # CO-R07 footerHint
├── stores/
│   └── workspace.ts                     # 可选 kbOpenFilename CO-R07
└── panels/__tests__/
    ├── commandsRegistry.test.ts         # CO-R10
    └── CommandsPanel.test.tsx           # CO-R10

docs/
└── COMMAND_SYSTEM.md                      # CO-R08 重写
```

---

## §10 PR 模板

```markdown
## Summary
参考双面板 redesign：知识库可读、对话指引与 command_parser 对齐；InputBar `/` 补全；删除假命令。

## 分工
- [ ] 知识库：分类中文、搜索、空态、tools chip
- [ ] 对话指引：3 命令 + 4 playbook + 互链
- [ ] InputBar：补全 + 填入
- [ ] COMMAND_SYSTEM.md 同步

## Test plan
- [ ] npm test
- [ ] §8.2 手工 1–7
```

**建议 commit message**：

```
feat(web): 参考双面板 redesign — 知识库可用 + 对话指引对齐 parser

- commandsRegistry 单源；对话指引重写（无 /confirm /how）
- rename 语法统一为 =；KnowledgePanel 分类与空态
- InputBar / 补全与填入输入框；更新 COMMAND_SYSTEM.md
```

---

## §11 预估工作量

**2～4 人天**（P0：CO-R01～R05、R08 ≈ 2d；P1：R06～R07 ≈ 1d；P2：R09 + 测试 ≈ 0.5～1d）。

建议编码顺序：R01 registry → R08 文档定稿 → R03 面板 → R04 知识库 → R05 InputBar → R06/R07 联动 → R10 测试。

---

## §12 与 sibling brief 关系

| 已完成 brief | 本 brief 关系 |
|--------------|---------------|
| Web UI v4 | 沿用 focusAreas、InputBar、侧栏四组；**不改** Analyze 流式/Copilot 逻辑 |
| 工具箱增强 | 知识库内容来源；**不改** methods 正文与 tool 注册 |
| Doctor §12（未做） | 不在范围；`tool_gate` 未来可校验 registry 与 parser 一致 |

---

*文档版本：v1 | 2026-06-12*
