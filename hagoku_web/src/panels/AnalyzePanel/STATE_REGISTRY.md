# AnalyzePanel 状态注册表

> 改以下任何代码前，必须逐项确认项目切换时的清理逻辑。
> 每次新增/删除/修改 state，必须同步更新本文件。
> 守门测试：`tests/test_frontend/test_state_registry.py`

## 本地 useState（AnalyzePanel.tsx）

| # | 状态 | 文件:行 | 默认值 | 切换时行为 | handler |
|---|------|--------|--------|-----------|---------|
| 1 | `phase` | AnalyzePanel.tsx:42 | `"setup"` | 重置为 `"setup"` | useEffect([currentProject]) ✅ |
| 2 | `queryText` | AnalyzePanel.tsx:43 | `""` | 清空 | useEffect([currentProject]) ✅ |
| 3 | `thinkingText` | AnalyzePanel.tsx:46 | `null` | 清空 | useEffect([currentProject]) ✅ |
| 4 | `replyPending` | AnalyzePanel.tsx:49 | `false` | 重置为 `false` | useEffect([currentProject]) ✅ |
| 5 | `dataPath` | AnalyzePanel.tsx:57 | `""` | 清空 | useEffect([currentProject]) ✅ |
| 6 | `excelSheets` | AnalyzePanel.tsx:86 | `[]` | 清空 | useEffect([currentProject]) ✅ |
| 7 | `sheetName` | AnalyzePanel.tsx:87 | `""` | 清空 | useEffect([currentProject]) ✅ |
| 8 | `auxSheets` | AnalyzePanel.tsx:88 | `[]` | 清空 | useEffect([currentProject]) ✅ |
| 9 | `presetName` | AnalyzePanel.tsx:52 | `""` | 清空 | useEffect([currentProject]) ✅ |

## hook 内部 state（useAnalyzeSession.ts）

| # | 状态 | 默认值 | 切换时行为 | handler |
|---|------|--------|-----------|---------|
| 10 | `agentElapsed` | `{scout:0,...}` | 重置为零 | sess.resetAll() ✅ |
| 11 | `waitingAgent` | `null` | 清空 | sess.resetAll() ✅ |
| 12 | `replyText` | `""` | 清空 | sess.resetAll() ✅ |
| 13 | `resultReportUrl` | `null` | 清空 | sess.resetAll() ✅ |
| 14 | `guardrailsBlocked` | `false` | 重置 | sess.resetAll() ✅ |
| 15 | `blockedRunId` | `null` | 清空 | sess.resetAll() ✅ |
| 16 | `activeFieldReviewId` | `null` | 清空 | sess.resetAll() ✅ |
| 17 | `activeFieldReviewRevision` | `-1` | 重置 | sess.resetAll() ✅ |
| 18 | `activeCleaningReviewId` | `null` | 清空 | sess.resetAll() ✅ |
| 19 | `activeCleaningReviewRevision` | `-1` | 重置 | sess.resetAll() ✅ |
| 20 | `activeAnalystReviewId` | `null` | 清空 | sess.resetAll() ✅ |
| 21 | `activeAnalystReviewRevision` | `-1` | 重置 | sess.resetAll() ✅ |
| 22 | `gateOpen` | `false` | 重置 | sess.resetAll() ✅ |
| 23 | `fieldReviewScrollNonce` | `0` | 重置 | sess.resetAll() ✅ |

## hook 内部 state（useFileUpload.ts）

| # | 状态 | 默认值 | 切换时行为 | handler |
|---|------|--------|-----------|---------|
| 24 | `projectFiles` | `[]` | 自动重载 | useFileUpload useEffect([currentProject]) ✅ |
| 25 | `filesLoading` | `false` | 自动重载 | useFileUpload useEffect([currentProject]) ✅ |
| 26 | `showFileDropdown` | `false` | 无需清理（关闭状态） | — |
| 27 | `showProjectDropdown` | `false` | 无需清理（关闭状态） | — |
| 28 | `uploading` | `false` | 无需清理 | — |
| 29 | `uploadError` | `null` | 无需清理 | — |
| 30 | `fileExists` | `false` | 自动检测 | useFileUpload useEffect([currentProject]) ✅ |

## hook 内部 state（useConversation.ts）

| # | 状态 | 默认值 | 切换时行为 | handler |
|---|------|--------|-----------|---------|
| 31 | `messages` | `[]` | 替换为新项目快照或清空 | handleStateSnapshot ✅ |

## workspace store（Zustand）

| # | 状态 | 切换时行为 | handler |
|---|------|-----------|---------|
| 32 | `status` | 不动（全局） | — |
| 33 | `agents` | `resetRunUiState()` | useEffect([currentProject]) ✅ |
| 34 | `currentProject` | ProjectPanel 已设置 | — ✅ |
| 35 | `currentDataPath` | 清空 | useEffect([currentProject]) ✅ |
| 36 | `snapshot` | 清空 | useEffect([currentProject]) ✅ |
| 37 | `lastError` | 清空 | useEffect([currentProject]) ✅ |
| 38 | `reportFiles` | 清空 | useEffect([currentProject]) ✅ |

## 统计

- **总状态数**：38
- **切换时需处理**：29
- **已处理**：29
- **缺失**：0
- **无需处理**：9（useFileUpload 自动 + status 全局 + currentProject 外部 + 下拉/上传临时状态）
