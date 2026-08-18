# HaGoKu Web UI

React 19 + Vite + TypeScript + Tailwind + Zustand. 与 HaGoKu 后端（FastAPI）通过 WebSocket 通信。

---

## 与后端的关系

Web UI **不是独立产品**，是 `hagoku` 后端的可视化前端。运行流程：

1. 后端：`hagoku-api` 启动 FastAPI（默认 `:8000`），同时挂载 `/ws`（WebSocket）和 `/api/*`（REST）
2. 前端：`npm run dev` 启动 Vite 开发服务器（默认 `:5173`）
3. Vite 通过 `server.proxy` 把 `/api` 和 `/ws` 反代到 `:8000`，前端无跨域问题
4. 生产构建：`npm run build` 产出 `dist/`，后端 `StaticFiles` 直接挂载

配置见 [`vite.config.ts`](vite.config.ts) — `API_PROXY` 把 `/api/*` 和 `/ws` 转发到 `http://127.0.0.1:8000`。

## 开发

```bash
# 前提：后端已起（hagoku-api）
cd hagoku_web
npm install
npm run dev          # 默认 http://localhost:5173
```

## 构建与预览

```bash
npm run build        # 产出 dist/
npm run preview      # vite preview（注意：preview 不走 server.proxy，需后端同进程或反代）
```

构建后，后端用 `hagoku/api/server.py:65` 的 `StaticFiles(html=True)` 把 `dist/` 挂在 `/`。

## 技术栈

| 层 | 技术 |
|----|------|
| 框架 | React 19.2 |
| 构建 | Vite 8 |
| 类型 | TypeScript 6（strict） |
| 样式 | Tailwind CSS 3.4 |
| 状态 | Zustand 5 |
| Markdown | react-markdown + remark-gfm |
| HTML 安全 | dompurify |
| 图标 | lucide-react |
| 测试 | Vitest + Testing Library + jsdom |

## 目录结构

```
hagoku_web/
├── src/
│   ├── components/       # 可复用 UI 组件（TitleBar, EventTable, …）
│   ├── hooks/            # 自定义 hooks（useWebSocket, useBatchEvents, …）
│   ├── panels/           # 8 个主面板
│   │   ├── ProjectPanel/    # 项目管理（含 __tests__/）
│   │   ├── AnalyzePanel/    # 分析对话（含 hooks/handlers.ts — 唯一状态写入点）
│   │   ├── ReportPanel/     # 历史报告浏览
│   │   ├── KnowledgePanel/  # 跨项目知识库
│   │   ├── SettingsPanel/   # LLM 配置
│   │   ├── PromptLabPanel/  # 预设编辑
│   │   ├── DoctorPanel/     # 诊断
│   │   └── EventPanel/      # 事件流调试
│   ├── stores/           # Zustand store（workspace.ts, theme.ts）
│   ├── types/            # TypeScript 类型
│   └── utils/            # 工具函数（含 wsGuardrails.ts 唯一真相源校验）
├── public/               # 静态资源
└── dist/                 # 构建产物（gitignored）
```

## 重要约束（修改前必读）

- **唯一真相源**：`AnalyzePanel/hooks/handlers.ts` 里的 `handleStateSnapshot` 是前端状态的**唯一写入点**。任何 `clearMessages`、`fetch.*switch`、`setCurrentDataPath` 都不能在 `handleStateSnapshot` 之外出现。参见 `utils/wsGuardrails.ts`
- **WS 协议**：前端只通过 `/ws` 接收状态更新，不直接 REST 写状态。所有写入通过后端事件总线

## 与后端联调

- **WebSocket 路径**：`/ws`
- **REST 前缀**：`/api/*`
- **开发**：Vite 已配 proxy，浏览器无需关心跨域
- **生产**：后端 `StaticFiles` 挂载 dist，`/ws` 和 `/api` 走同一端口（`:8000`）

---

**变更记录**

| 日期 | 内容 |
|------|------|
| 2026-08-18 | 替换 Vite 模板默认 README，写入项目特定内容 |