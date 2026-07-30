# 项目切换架构 — 设计文档 v6

> 状态：v6 整体性审计后重写。
> 核心：说明「prevRef 守卫 + App.tsx 启动恢复」是一个方案的互补两半，
> 不是为了打补丁加的第二个入口。标注残留代码 + 竞态风险。

## 一、整体方案（为什么有两个入口）

**问题**：`AnalyzePanel` 的 `useEffect([currentProject])` 需要区分「首次挂载」和「真正切换」——
首次挂载时 WS 快照可能尚未到达，不能清空消息（否则快照到达前的空窗期用户看到空白）；
真正切换时必须清理 UI 状态（否则旧项目数据残留）。

**方案**：prevRef 守卫 + App.tsx 启动恢复，互为补充：

```
应用启动
  │
  ├─ AnalyzePanel mount → prevRef 守卫跳过清理（prev===null）
  │     （此时快照尚未到达，消息为空，不做任何操作）
  │
  └─ App.tsx mount → useEffect send("switch_project", {proj})
        → 后端恢复 session → WS state_snapshot → handleStateSnapshot
        → syncFromSnapshot(48条消息) + setPhase("running")
        → 用户看到历史对话 ✅

用户点击切换 A→B
  │
  └─ ProjectPanel → setCurrentProject("B") + send("switch_project", {B})
       │
       ├─ AnalyzePanel useEffect: prev="A" current="B" → 执行清理
       │     （清空本地 UI 状态，不碰 messages）
       │
       └─ WS state_snapshot 到达 → handleStateSnapshot
            → syncFromSnapshot(B的消息) + setPhase("running")
```

**结论**：只有一个数据通道（WS `state_snapshot` → `handleStateSnapshot`），
两个入口（`App.tsx:135`、`ProjectPanel.tsx:489`）都走这个通道。
prevRef 守卫确保首次挂载不误清，App.tsx 填补首次挂载的恢复需求。
不是补丁，是一体设计。

## 二、竞态风险（已知，未修复）

| 风险 | 触发条件 | 影响 | 缓解 |
|------|---------|------|------|
| WS 快照在 useBatchEvents 注册前到达 | App mount 时 WS 连接快于 React effect 执行 | 快照丢失，用户看到空白 | 暂无。需 `useBatchEvents` 缓存早期消息 |
| WS 断连时启动恢复 | 网络不通时打开应用 | App.tsx 发了 switch_project 但无响应，phase 保持 setup | 无影响（setup 是正确的降级状态） |
| 连续快速切换 | A→B→C 快速点击 | 两个快照几乎同时到达，React 批量处理，最终以最后一个为准 | 正确行为 |

## 三、代码纯净度——残留项

| 文件:行 | 内容 | 状态 |
|---------|------|:--:|
| `app.py:126-128` | `logger.info/warning` debug 日志 | ⚠️ 待移除（根因已修复，无需保留） |
| `handlers.ts:32` | `addSystemMsg: addSys` 解构但未使用 | ⚠️ 待清理 |

## 四、数据流（单通道，双入口）

```
┌─ 入口1: 启动恢复 ──┐    ┌─ 入口2: 手动切换 ──┐
│ App.tsx:135          │    │ ProjectPanel.tsx:489 │
│ send("switch_project",│    │ send("switch_project",│
│   {project:proj})    │    │   {project:p})       │
└──────┬───────────────┘    └──────┬───────────────┘
       └──────────┬────────────────┘
                  ▼
         useWebSocket.ts:190
         _ws.send(JSON.stringify({cmd, payload}))
                  │
                  ▼  WS消息: {"cmd":"switch_project","payload":{"project":"X"}}
                  │
         ws_handler.py:294
         name = (msg.get("payload") or msg).get("project", "")
                  │
         app.py:90  switch_project(name)
           → app.py:110  _load_project(name)
             → orchestrator.py:171  restore_session()
           → app.py:118  build_snapshot()
                  │
         ws_handler.py:309
         state_snapshot → WS push
                  │
         handleStateSnapshot (handlers.ts:28)
           → syncFromSnapshot(ms) (useConversation.ts:113)
           → setPhase("running")
```

**唯一写入点：** `handleStateSnapshot`（`handlers.ts:60` `syncFromSnapshot` / `:63` `_setMessages`）。
`AnalyzePanel.tsx:127-151` useEffect 清理 UI 状态但不写 messages（铁律 13 合规）。

## 五、实施改动清单（含代码证据）

| # | 改动 | 文件:行 | 阶段 |
|---|------|--------|:--:|
| A | `_processing` flag | `orchestrator.py:74` | 0 |
| B | `_processing = True` on respond | `reply_handlers.py:108` | 0 |
| C | `_processing = False` in finally | `reply_handlers.py:122` | 0 |
| D | `_processing = False` on cancel | `orchestrator.py:237` | 0 |
| E | `is_busy()` → `_processing` | `app.py:88` | 0 |
| F | `resetAll()` 14 setter | `useAnalyzeSession.ts:42-57` | 1 |
| G | `handleReset`/`handleStartSession` 复用 | `useAnalyzeSession.ts:59-87` | 1 |
| H | `useEffect([currentProject])` + prevRef | `AnalyzePanel.tsx:127-151` | 1 |
| I | `handleStateSnapshot` 删守卫 | `handlers.ts` — 行 46-54 已删 | 2 |
| J | `build_snapshot` `or ""` | `app.py:232-233` | 3 |
| K | `STATE_REGISTRY.md` + 守门测试 | 新文件 | 4 |
| L | `ws_handler` payload 路径修复 | `ws_handler.py:294,313,317` | 5 |
| M | `App.tsx` 启动恢复 | `App.tsx:131-137` | 5 |
| N | 移除 debug 日志 | `app.py:126-128` | 待做 |
| O | 清理未使用解构 | `handlers.ts:32` | ✅ 已做 |

---

## 五、分阶段实施

每个阶段有 **进入条件、改动清单、完成审核、通过标准**。
不通过 → 不回退 → 在当前阶段修到通过为止。

### 阶段 0：`is_busy()` 语义修复

**目标**：分析正常完成后 `is_busy()` 返回 False，允许切换项目。

**进入条件**：代码仓库干净，`pytest tests/` 全绿。

**改动**：A, B, C, D, E（3 文件，+6 行）

**完成审核**：
```bash
grep -n "_processing" hagoku/manager/orchestrator.py hagoku/manager/llm_dispatch/reply_handlers.py hagoku/app.py
# 预期：orchestrator.py:74=False, :237=False; reply_handlers.py:108=True, :122=False; app.py:88=return _processing
```

**通过标准**：
- [ ] `pytest tests/` 全绿
- [ ] 手动验证：分析完成 → 点其他项目 → 不出现"分析进行中"提示

**通过即进入阶段 1。**

---

### 阶段 1：前端切换清理

**目标**：用户切换项目时，AnalyzePanel 自动重置 9 个本地 state + 14 个 sess state + 5 个 store 字段。不碰 messages（铁律 13）。

**进入条件**：阶段 0 通过。

**改动**：F, G, H（2 文件，+45/-28 行）

**完成审核**：
```bash
# resetAll 14 setter
grep -c "set[A-Z]" hagoku_web/src/panels/AnalyzePanel/hooks/useAnalyzeSession.ts | head -1
# handleReset/handleStartSession 均调 resetAll()
grep -B2 "resetAll()" hagoku_web/src/panels/AnalyzePanel/hooks/useAnalyzeSession.ts
# useEffect deps 只有 currentProject
grep "}, \[currentProject\]" hagoku_web/src/panels/AnalyzePanel.tsx
# 无 clearMessages
grep -c "clearMessages" hagoku_web/src/panels/AnalyzePanel.tsx
# 预期：=1（仅在 useConversation 解构行）
```

**通过标准**：
- [ ] `npx tsc --noEmit` 零错误
- [ ] `pytest tests/` 全绿
- [ ] 手动验证 S3：切项目后 UI 不残留旧数据
- [ ] 手动验证 S8：A→B→A→B 反复切，每次正确

**通过即进入阶段 2。**

---

### 阶段 2：handleStateSnapshot 精简

**目标**：删除守卫行 46-54，职责移给阶段 1 的 useEffect。保留消息同步、agent 状态条、项目删除处理。

**进入条件**：阶段 1 通过。

**改动**：I（1 文件，-15/+5 行）

**完成审核**：
```bash
# 旧守卫已删除
grep "snap.project_name.*deps.currentProject" hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts
# 预期：无输出
# 消息同步保留
grep -c "syncFromSnapshot\|roleMap\|toolExchange" hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts
# 预期：>=5
# 项目删除保留
grep -c "项目被删除" hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts
# 预期：1
```

**通过标准**：
- [ ] `npx tsc --noEmit` 零错误
- [ ] 手动验证 S3/S4：快照消息正确渲染

**通过即进入阶段 3。**

---

### 阶段 3：build_snapshot 防 None

**目标**：`data_path`/`query` 空值时返回 `""` 而非 `None`。

**进入条件**：阶段 2 通过。

**改动**：J（1 文件，+1/-1 行）

**完成审核**：
```bash
grep 'or ""' hagoku/app.py | grep "data_path\|query"
# 预期：2行
```

**通过标准**：
- [ ] `pytest tests/` 全绿
- [ ] 手动验证 S4：空项目快照不返回 None

**通过即进入阶段 4。**

---

### 阶段 4：STATE_REGISTRY + 守门测试

**目标**：锁死 38 个状态清单。后续增删 state 必须同步更新注册表。

**进入条件**：阶段 3 通过。

**改动**：K（2 个新文件，+140 行）

**完成审核**：
```bash
pytest tests/test_frontend/test_state_registry.py -v
# 预期：3 passed
```

**通过标准**：
- [ ] `pytest tests/test_frontend/test_state_registry.py` 3 passed
- [ ] 守门测试能拦住改动：临时加一个 useState → 测试失败

**通过即进入阶段 5。**

---

### 阶段 5：WS 消息格式修复 + 启动恢复

**目标**：修复根因 ⑦（ws_handler 取不到 project），补上启动恢复（App mount 自动 switch）。

**进入条件**：阶段 4 通过。

**改动**：L, M（2 文件，+11/-3 行）

**完成审核**：
```bash
# payload 路径修复
grep -c "msg.get.*payload.*or.*msg" hagoku/api/ws_handler.py
# 预期：3
# 启动恢复
grep -A3 "挂载后恢复" hagoku_web/src/App.tsx | grep "send.*switch_project"
# 预期：1行匹配
```

**通过标准**：
- [ ] `npx tsc --noEmit` 零错误
- [ ] `pytest tests/` 全绿
- [ ] WS 端到端：`switch_project test0729` 返回 48 条消息
- [ ] 手动验证 S1：重启应用 → test0729 对话自动出现
- [ ] 手动验证 S2：新建项目后重启 → setup 界面

**全部阶段通过 → 提交。**

---

### 阶段总览

| 阶段 | 做什么 | 文件数 | 行数 | 关键审核 | 通过标志 |
|:--:|------|:--:|:--:|------|------|
| 0 | is_busy 语义修复 | 3 | +6 | `_processing` flag 4 处正确 | pytest 全绿 |
| 1 | 前端切换清理 | 2 | +45/-28 | resetAll + prevRef + 无 clearMessages | tsc + 手动 S3/S8 |
| 2 | handleStateSnapshot 精简 | 1 | -15/+5 | 守卫删、核心逻辑保留 | tsc + 手动 S3/S4 |
| 3 | build_snapshot 防 None | 1 | +1/-1 | `or ""` ×2 | pytest + 手动 S4 |
| 4 | 状态注册表 | 2 | +140 | 3 守门测试 | pytest 守门通过 |
| 5 | WS 修复 + 启动恢复 | 2 | +11/-3 | payload 路径 + App mount | WS 端到端 + S1/S2 |
| **合计** | | **10** | **~175** | | |

## 六、验收场景

| # | 场景 | 预期 |
|---|------|------|
| S1 | 启动恢复（有历史） | test0729 对话自动出现 |
| S2 | 启动恢复（无历史） | setup 界面 |
| S3 | 手动切换 A→B（B 有历史） | B 对话出现 |
| S4 | 手动切换 A→B（B 无历史） | setup 界面 |
| S5 | 分析进行中→切换 | 被拒绝 |
| S6 | 停止→切换 | 正常 |
| S7 | A→B→A→B 反复切 | 每次正确 |
| S8 | 删除项目→自动清 | setup |

## 七、文件改动清单

| 文件 | 改动 | 行数 |
|------|------|:--:|
| `orchestrator.py` | `_processing` flag | +3 |
| `reply_handlers.py` | try/finally | +3 |
| `app.py` | `is_busy()` + `build_snapshot` | +2/-1 |
| `ws_handler.py` | payload 路径修复 ×3 | +3/-3 |
| `App.tsx` | 启动恢复 useEffect | +8 |
| `AnalyzePanel.tsx` | useEffect + prevRef | +25 |
| `handlers.ts` | 删守卫 | -15/+5 |
| `useAnalyzeSession.ts` | `resetAll()` + 复用 | +20/-28 |
| `STATE_REGISTRY.md` | 新建 | +76 |
| `test_state_registry.py` | 新建 | +64 |
| **待清理** | `app.py:126-128` debug 日志 | -2 |
| **待清理** | `handlers.ts:32` 未用解构 | -1 |
| **合计** | **10 文件** | **~175 行净增** |

## 八、怎么实施

### 步骤 1：清理残留（5 分钟）
```bash
# 1.1 移除 app.py debug 日志
#     删除 app.py:126-128 两行 logger.info/warning

# 1.2 清理 handlers.ts 未用解构
#     删除 handlers.ts:32 的 addSystemMsg: addSys,
```

### 步骤 2：确认代码（2 分钟）
```bash
# 逐项核对改动清单 A-O，确认每项代码存在且行号准确
grep -n "_processing = False" hagoku/manager/orchestrator.py  # A
grep -n "_processing = True" hagoku/manager/llm_dispatch/reply_handlers.py  # B
grep -n "_processing = False" hagoku/manager/llm_dispatch/reply_handlers.py  # C
grep -n "_processing = False" hagoku/manager/orchestrator.py  # D
grep -n "return self._active_orch._processing" hagoku/app.py  # E
grep -n "const resetAll" hagoku_web/src/panels/AnalyzePanel/hooks/useAnalyzeSession.ts  # F
grep -n "resetAll()" hagoku_web/src/panels/AnalyzePanel/hooks/useAnalyzeSession.ts  # G
grep -n "prevProjectRef" hagoku_web/src/panels/AnalyzePanel.tsx  # H
grep -n "项目切换时的清理由" hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts  # I
grep -n "or \"\"" hagoku/app.py | grep "data_path\|query"  # J
ls hagoku_web/src/panels/AnalyzePanel/STATE_REGISTRY.md tests/test_frontend/test_state_registry.py  # K
grep -n "msg.get.*payload.*or.*msg" hagoku/api/ws_handler.py  # L
grep -n "send.*switch_project" hagoku_web/src/App.tsx  # M
```

### 步骤 3：运行测试（3 分钟）
```bash
cd hagoku_web && npx tsc --noEmit          # TS 零错误
cd .. && python3 -m pytest tests/ -q         # pytest 全绿
python3 -m pytest tests/test_frontend/test_state_registry.py -v  # 守门测试 3 passed
```

### 步骤 4：重启服务（1 分钟）
```bash
pkill -f hagoku-api; pkill -f "vite.*hagoku"
HAGOKU_API_RELOAD=0 hagoku-api &
cd hagoku_web && npx vite --host 0.0.0.0 --port 5173 &
```

### 步骤 5：提交（1 分钟）
```bash
git add -A
git commit -m "fix: 项目切换完整修复

根因: ws_handler msg.get('project') 取不到值（send包装为{cmd,payload}）
修复: (msg.get('payload') or msg).get('project', '') ×3
附带: is_busy _processing、useEffect+prevRef、App启动恢复、resetAll重构
【自检】tsc零错误, pytest全绿, WS端到端48条消息"
```

## 九、怎么验证

每项场景的 **精确操作步骤** 和 **判定标准**。

### S1：启动恢复（有历史）
| 步骤 | 操作 | 停留/观察 | 判定 |
|------|------|----------|------|
| 1 | 关闭桌面应用 | — | — |
| 2 | 确认 API 运行中 | `curl localhost:8000/docs` → 200 | — |
| 3 | 启动桌面应用 | 等待 3 秒 | — |
| 4 | 观察分析面板 | — | 看到 test0729 的对话，字段理解表/清洗评估/分析发现等内容出现 |
| ❌ | 不通过 | 看到 setup 界面或空白 | 查 hagoku.log 最后 5 行 |

### S2：启动恢复（无历史）
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 新建空项目 test_empty | — |
| 2 | 关闭桌面应用 | — |
| 3 | 重启应用 | 分析面板为 setup 界面，无报错 |

### S3：手动切换 A→B（B 有历史）
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 当前在 test0729 | 对话可见 |
| 2 | 点击项目列表中的 test0729V3 | — |
| 3 | 再点击 test0729 | test0729 对话恢复 |
| ❌ | 不通过 | 切换后内容不变或空白 |

### S4：手动切换 A→B（B 无历史）
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 当前在 test0729 | 对话可见 |
| 2 | 点击 test0729V2（无历史） | setup 界面，无残留 |

### S5：分析进行中→切换
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 启动分析 | — |
| 2 | 分析进行中点其他项目 | 提示"当前项目分析进行中"，不切换 |

### S6：停止→切换
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 分析进行中点停止 | — |
| 2 | 点其他项目 | 正常切换 |

### S7：反复切换
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | test0729 → test0729V3 → test0729 → test0729V3 | 每次切换内容正确，不残留不重复 |

### S8：删除项目
| 步骤 | 操作 | 判定 |
|------|------|------|
| 1 | 当前在 test0729 | 对话可见 |
| 2 | 删除 test0729 | 分析面板自动清空 → setup |

## 十、怎么审核

每处改动的 **审核命令**、**预期输出**、**全局影响检查**。

| # | 改动 | 审核命令 | 预期 | 全局影响 |
|---|------|---------|------|---------|
| A | `orchestrator.py:74` `_processing=False` | `grep -n "_processing" hagoku/manager/orchestrator.py` | 行 74 和 237 各有 `_processing = False` | 无（构造初始化） |
| B | `reply_handlers.py:108` `_processing=True` | `grep -n "_processing" hagoku/manager/llm_dispatch/reply_handlers.py` | 行 108 `True`, 行 122 `False`(finally) | respond 入口，finally 保证异常后恢复 |
| C | `reply_handlers.py:122` `finally` | 同上 | 同上 | 任何异常路径都清 `_processing` |
| D | `orchestrator.py:237` cancel 清 `_processing` | 同上 A | 行 237 `_processing = False` | 停止后 `is_busy()` 返回 False |
| E | `app.py:88` `is_busy()` | `grep -A2 "def is_busy" hagoku/app.py` | `return self._active_orch._processing` | 影响 ws_handler:297 和 server.py:182 |
| F | `useAnalyzeSession.ts:42-57` resetAll | `grep -c "set[A-Z]"` 数 14 个 setter | 14 | handleStartSession/handleReset 均复用 |
| G | `useAnalyzeSession.ts:59-87` 复用 | `grep "resetAll()"` 所在函数 | handleStartSession 和 handleReset 内 | 不改变原行为 |
| H | `AnalyzePanel.tsx:127-151` useEffect | `grep -A25 "prevProjectRef"` | 三个跳过条件 + 清理逻辑 | 仅项目切换触发 |
| I | `handlers.ts` 删守卫 | `grep "snap.project_name.*deps.currentProject"` | 无输出（已删除） | 重连时 project_name 相同 → 不受影响 |
| J | `app.py:232-233` or "" | `grep 'or ""' hagoku/app.py` | query 和 data_path 行 | 仅影响 build_snapshot 输出 |
| K | STATE_REGISTRY + 守门 | `pytest tests/test_frontend/test_state_registry.py -v` | 3 passed | 新增文件，零影响 |
| L | `ws_handler.py:294,313,317` payload | `grep "msg.get.*payload.*or.*msg" hagoku/api/ws_handler.py` | 3 行匹配 | 同时修了 switch/create/delete |
| M | `App.tsx:131-137` 启动恢复 | `grep -A5 "挂载后恢复" hagoku_web/src/App.tsx` | send("switch_project") | 仅 mount 一次，无副作用 |
| N | `app.py:126-128` 移除 | `grep "logger.info.*_load_project" hagoku/app.py` | 无输出 | — |
| O | `handlers.ts:32` 清理 | `grep "addSystemMsg" hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts` | 仅 `addSystemMsg: addSys` 已删除 | 原已未使用 |

### 全系统回归

```bash
# 1. TypeScript
cd hagoku_web && npx tsc --noEmit

# 2. Python 全量
cd .. && python3 -m pytest tests/ -q

# 3. 铁律守门
python3 -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q

# 4. 消息写入点合规
grep -rn 'setMessages' hagoku_web/src/panels/AnalyzePanel/ --include='*.ts' --include='*.tsx' \
  | grep -v 'useConversation' | grep -v 'types.ts' | grep -v '_setMessages' | grep -v '__tests__'
# 预期：无输出

# 5. clearMessages 合规
grep -n 'clearMessages' hagoku_web/src/panels/AnalyzePanel.tsx
# 预期：仅在 useConversation 解构行（109），不在 useEffect 内
```
