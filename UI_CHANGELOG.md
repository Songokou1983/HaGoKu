# UI 改动日志

## 2026-05-12 — 文档同步（Web UI 与人机互动理念）

- **PROJECT.md**：新增「人机互动理念」；删除/替换残留「用户三模式」叙述；CLI 表与模板默认说明对齐代码（`default` 双轨、无 `--mode`）；技术选型与 V2 交付物改为当前 **非 dockview** 的固定导航 SPA。
- **README.md / docs/DEVELOPMENT.md / DEV.md**：Web UI 描述、手动测试步骤、`report --template` 说明、配置示例与环境变量表与上述一致；移除已不生效的 `HAGOKYU_MANAGER_MODE` / `manager.mode` 编排档位描述。
- **`.env.example`**：删除 `HAGOKYU_MANAGER_MODE` 占位行。
- **`DEVELOPMENT_PROMPT.md`**：改为**可重复填写的任务传递模板**（非废弃），并指向 `PROJECT.md` 等现行口径；历史长文已移除以防误导。
- **文档索引**：`PROJECT.md` / `DEV.md` / `CLAUDE.md` 的文档表补充 `DEVELOPMENT_PROMPT.md` 条目。

## 2026-05-09 — WebUI 优化（第二轮）

### 变更概要

针对 React 前端代码库进行了全面优化，消除运行时性能问题、类型不安全引用和冗余逻辑。

### 优化清单

| # | 变更 | 文件 | 说明 |
|---|------|------|------|
| 1 | 扩展类型定义 | `types/events.ts` | 新增 `AgentId` 联合类型（scout/cleaner/analyst/reporter）；`AgentStatus` 新增 `running`、`waiting_input` 值 |
| 2 | 修复 busy → running | `useAgentStatusSync.ts` | `agent_started` 事件映射从 `"busy"` 改为 `"running"`，与类型定义对齐 |
| 3 | 修复 busy → running | `App.tsx` | `SystemStatus` 组件中 `filter(s === "busy")` 改为 `filter(s === "running")` |
| 4 | 规范 Props 接口 | `PanelHeader.tsx` | 提取独立 `PanelHeaderProps` 接口；使用 `useCallback` 包裹 toggle 回调 |
| 5 | 提取 EmptyState 组件 | `EmptyState.tsx`（新建） | 从各面板内联样式统一为可复用无数据占位组件 |
| 6 | ErrorBoundary 组件 | `ErrorBoundary.tsx`（新建） | React class-based 错误边界，包裹每个面板防止单点崩溃白屏 |
| 7 | ConnectionIndicator | `ConnectionIndicator.tsx`（新建） | WebSocket 连接状态指示灯组件，按 disconnected/reconnecting/connecting/connected 显示不同颜色 |
| 8 | LogView 自动滚动 | `LogView.tsx` | 新增消息时自动滚动到底部，防止新日志被遮挡 |
| 9 | InputBar 优化 | `InputBar.tsx` | `useCallback` 包裹 submit/key 处理函数；通过 ref 直接操作 textarea 避免不必要的 re-render |
| 10 | EventTable 虚拟化 | `EventTable.tsx` | 引入 `@tanstack/react-virtual` 虚拟滚动，大量事件列表渲染性能提升 |
| 11 | 面板级 useMemo/useCallback | 所有 6 个 Panel | 面板组件内派生数据使用 useMemo 缓存；回调使用 useCallback 稳定引用 |
| 12 | WebSocket 心跳优化 | `useWebSocket.ts` | 连接空闲时降低 pingInterval；重连指数退避（1s → 30s，max 5 次后固定 30s） |
| 13 | Dockview 高度修复 | `App.tsx` | 外层 CSS Grid `gridTemplateRows: "auto 1fr"` + `minHeight: 0` 确保 dockview 正确获得固定高度 |

### 验证状态

| 检查项 | 结果 |
|--------|------|
| TypeScript 类型检查 | ✅ 零错误 |
| Vite 生产构建 | ✅ 成功（1754 modules，493KB JS + 103KB CSS，129KB gzip） |
| 所有面板 0 TypeScript Error | ✅ |

---

## 2026-05-09 — 架构重构：Streamlit → React + FastAPI

### 动机

旧 Streamlit WebUI（`hagoku/ui/`）存在以下问题：
- 页面/组件耦合度高，不支持面板拖拽布局
- Python 单页应用，无法利用现代前端生态
- 无实时 WebSocket 事件流，分析进度不可见
- 深色主题和 IDE 风格体验缺失

### 新架构

```
hagoku_web/ (React + TypeScript + Vite)  ← 前端
hagoku/api/  (FastAPI + WebSocket)       ← 后端
```

| 组件 | 旧（Streamlit） | 新（React + FastAPI） |
|------|----------------|----------------------|
| 框架 | Streamlit (Python) | React 19 + TypeScript + Vite 8 |
| 布局 | 固定侧边栏 + 主区域 | dockview 可拖拽面板（tabs/groups/grids） |
| 通信 | HTTP 轮询 | WebSocket 实时事件流 |
| 样式 | Streamlit 默认主题 | 深色 VSCode 风格（CSS 变量） |
| 图标 | emoji | lucide-react |
| 状态管理 | Streamlit session_state | Zustand (workspace store) |
| 构建产物 | 无（运行时渲染） | 487KB JS + 92KB CSS (126KB gzip) |

### 面板迁移对照

| 旧页面（Streamlit） | 新面板（React） | 文件 |
|---------------------|----------------|------|
| `app_projects.py` | **Projects** | `panels/ProjectPanel.tsx` |
| `app_analyze.py` | **Analyze** | `panels/AnalyzePanel.tsx` |
| `app_report.py` | **Reports** | `panels/ReportPanel.tsx` |
| `app_knowledge.py` | **Knowledge** | `panels/KnowledgePanel.tsx` |
| `app_settings.py` | **Settings** | `panels/SettingsPanel.tsx` |
| `event_log.py` | **Event Log** | `panels/EventPanel.tsx` |

### 新增后端 API

| 文件 | 职责 |
|------|------|
| `hagoku/api/server.py` | FastAPI app + CORS + 静态文件挂载（Vite dist） |
| `hagoku/api/ws_handler.py` | WebSocket `/ws` 端点：事件广播、心跳、分析命令处理 |
| `hagoku/api/__init__.py` | 模块导出 |

### 启动方式变更

**旧：** `hagoku-ui` → http://localhost:8501（Streamlit）

**新：**
```bash
# 终端 1：后端
hagoku-api          # http://localhost:8000

# 终端 2：前端
cd hagoku_web && npm run dev   # http://localhost:5173
```

### 删除的文件

- `hagoku/ui/` 整个目录（已废弃）
- 旧 Streamlit 组件：`event_log.py`, `file_uploader.py`, `folder_picker.py`, `project_sidebar.py`, `report_viewer.py`
- `hagoku/ui/components/folder_picker_component/`

### pyproject.toml 变更

- **删除依赖：** `streamlit`
- **新增依赖：** `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`
- **新增脚本：** `hagoku-api = "hagoku.api.server:main"`

### 验证状态

| 检查项 | 结果 |
|--------|------|
| TypeScript 类型检查 | ✅ 零错误 |
| Vite 生产构建 | ✅ 成功（1744 modules） |
| Python 导入检查 | ✅ 通过 |

---

## 2026-05-05

### 项目管理页面 (app_projects.py)

1. 删除顶部统计栏（项目数/总分析次数/总数据文件/总存储 metric boxes）
2. 删除展开详情中的"项目记忆"模块（记忆笔记 text_area + 保存记忆按钮）
3. 删除整个展开详情模块（数据文件列表、过程文件列表）
4. 将"创建于/最近更新时间"从第二行移到第一行（项目名后面）
5. 编辑弹窗中加入文件清单及删除文件功能
6. 项目概况标题调大字体(html h2标签，2.5rem，cyan #00ffff)