# 多项目架构设计

> v0.9 → v0.10 | 2026-06-25

## 目标

HaGoKu 从单项目变为多项目系统。每个项目独立存储、独立会话、独立状态。前端切项目时自动切换分析面板内容。重连时恢复到关闭前所在项目和对话状态。

---

## 一、项目文件夹结构

每个项目是一个独立的文件夹，拷贝即可迁移：

```
~/.hagoku/projects/{project_name}/
├── project.json                  # 项目元数据
│   ├── name: str                 #   项目名
│   ├── created_at: str           #   创建时间
│   ├── data_file: str            #   当前数据文件路径
│   └── current_run_id: str       #   当前活跃 run（空=无分析）
│
├── data/                         # 用户上传的数据文件
│   └── *.xlsx, *.csv
│
├── memory.json                   # 项目记忆（LLM 确认的字段定义）
│   └── fields: {                 #   col_name → { display_name, description, confirmed }
│       "Inc1": {"display_name": "店铺收入", "description": "...", "confirmed": true}
│   }
│
├── reports/                      # 报告入口
│   └── latest.html               #   符号链接 → runs/{latest}/output/report.html
│
└── runs/                         # 每次分析运行一个子目录
    └── {run_id}/
        ├── run_meta.json         #   运行元数据
        ├── orch_state.json       #   编排器状态快照（恢复用）
        ├── session.json          #   对话历史
        ├── run.log               #   执行日志
        ├── llm_dumps/            #   LLM 交互 dump
        ├── df_raw.parquet        #   原始数据快照
        └── output/
            ├── charts/           #   图表 HTML
            └── report.html       #   分析报告
```

### 和现在的差异

| | 现在 | 改后 |
|---|------|------|
| 项目文件夹 | data/ + runs/ | 加 project.json + memory.json + reports/ |
| `project.json` | 不存在 | 新增，记录元数据 |
| `memory.json` | 不存在（在 SQLite） | 新增，从 SQLite 同步 |
| `reports/latest.html` | 不存在 | 新增，符号链接到最新报告 |
| 多项目支持 | 单 `_shared_orchestrator` | ProjectManager 管理当前项目 |

---

## 二、后端：ProjectManager

### 内存模型

只持有**当前活跃项目**的 Orchestrator。切换项目时：当前项目存盘 → 清空 → 新项目从磁盘加载。

```
ProjectManager
├── _current_project: str | None
├── _current_orchestrator: Orchestrator | None
└── 其他项目状态全在磁盘上
```

**为什么不用 dict 存所有项目**：数据量小（620行×8列仅几十KB），磁盘加载毫秒级。单例模型更简单、无内存压力、避免多项目并发问题。

### 核心类

```python
class ProjectManager:
    """管理所有项目的生命周期"""

    _current_project: str | None = None
    _current_orch: Orchestrator | None = None

    def switch_project(self, project_name: str) -> dict:
        """切换到目标项目。
        1. 如果当前项目有活跃分析 → 拒绝切换
        2. 保存当前项目状态到磁盘
        3. 清空 _current_orch
        4. 从磁盘恢复目标项目 → 返回快照
        5. 磁盘无 → 创建新 orchestrator
        """

    def get_current_orch(self) -> Orchestrator:
        """获取当前项目的 orchestrator"""

    def run_analysis(self, data_path: str, query: str):
        """为当前项目启动新分析。"""

    def respond(self, text: str) -> dict:
        """处理用户回复。"""

    def get_snapshot(self) -> dict:
        """返回当前项目状态快照"""

    def cancel_respond(self):
        """取消当前 respond 处理"""

    def delete_project(self, project_name: str):
        """删除项目文件夹"""
```

### 和现在的差异

- 现有全局变量 `_shared_orchestrator` 改为 `_project_manager._current_orch`
- WS 命令不需要 `project` 字段（始终操作当前项目）
- 切项目通过 `switch_project` 命令显式执行

### 项目切换限制

如果当前项目有活跃的 LLM 调用（`replyPending`），**禁止切换**。前端弹出提示"当前项目分析进行中，请等待完成或停止后再切换"。完整分析跨度太长，不应让用户等。

### 初始化流程

```
应用启动
  → ProjectManager 初始化
  → 扫描 projects/ 目录，找所有 project.json
  → 找到有 current_run_id 的项目 → 恢复 orchestrator
  → 前端连接 → 推送项目列表 + 上次打开的项目快照
```

---

## 三、WS 协议

当前项目由 `switch_project` 设定，后续命令不需要 `project` 字段。

```json
// 项目列表
{"cmd": "list_projects"}
// 切换项目
{"cmd": "switch_project", "project": "test0625"}
// 新建项目
{"cmd": "create_project", "project": "新项目"}
// 删除项目
{"cmd": "delete_project", "project": "test0625"}
// 分析（使用当前项目）
{"cmd": "analyze", "payload": {"data_path": "...", "query": "..."}}
// 回复
{"cmd": "respond", "payload": {"text": "Inc1是收入"}}
// 取消回复
{"cmd": "cancel_respond"}
// 取消分析
{"cmd": "cancel_analysis"}
```

`switch_project` 响应：
```json
{
  "type": "state_snapshot",
  "data": {
    "project_name": "test0625",
    "query": "分析每个店铺的收入变动趋势",
    "data_path": "/home/.../data.xlsx",
    "messages": [...],
    "pending_ask_user": {...},
    "report_url": "..."
  }
}
```

---

## 四、前端

### 状态管理

前端不缓存多项目状态。切项目时清空分析面板，等待后端 snapshot 恢复渲染。

```typescript
interface WorkspaceState {
  currentProject: string | null;
  projectList: string[];
  connectionStatus: ConnectionStatus;
  replyPending: boolean;  // 用于禁止项目切换
}
```

### 项目切换流程

```
用户点击项目B
  ↓
1. replyPending? → 提示"分析进行中，无法切换" → 拒绝
2. 清空分析面板（messages、review 表、thinking 等）
3. 发送 {"cmd": "switch_project", "project": "B"}
4. 接收 state_snapshot → 恢复对话和状态 → 渲染
```

### UI 改动

| 组件 | 改动 |
|------|------|
| ProjectPanel | 项目列表 + 新建/删除/切换 |
| AnalyzePanel | 监听 currentProject 切换 → 清空并重新加载 |
| ReportPanel | 显示当前项目的报告 |
| 标题栏 | 显示当前项目名 |

---

## 五、实现顺序

| 步骤 | 内容 | 文件 | 依赖 |
|------|------|------|------|
| 1 | 项目文件夹结构化 | orchestrator.py（save_state 写 project.json + memory.json）| 无 |
| 2 | ProjectManager 类 | 新建 `hagoku/manager/project_manager.py` | 步骤 1 |
| 3 | ws_handler 适配 ProjectManager | ws_handler.py（_shared_orchestrator → _project_manager）| 步骤 2 |
| 4 | 前端项目选择 + 切换逻辑 | workspace.ts + ProjectPanel.tsx + AnalyzePanel.tsx | 步骤 3 |
| 5 | 报告页项目感知 | ReportPanel.tsx | 步骤 4 |
| 6 | 清理全局单例 + 旧代码删除 | 全局变量 → ProjectManager 属性 | 步骤 2 |

### 各步骤详情

**步骤 1：项目文件夹结构化**
- `save_state()` 追加写入 `~/.../projects/{name}/project.json`
- `run_scout_phase` 完成后同步 `memory.json`
- `generate_report` 完成后更新 `reports/latest.html` 符号链接

**步骤 2：ProjectManager**
- 新建类，封装当前项目 Orchestrator
- `switch_project()` 含保存→清空→加载→快照
- `get_snapshot()` 复用现有 `_build_state_snapshot`
- 启动时扫描 `projects/` 目录构建项目列表

**步骤 3：ws_handler 适配**
- 现有 `_shared_orchestrator` → `_project_manager.get_current_orch()`
- 新增 `switch_project`、`create_project`、`delete_project`、`list_projects` 命令
- `respond`/`analyze`/`cancel_*` 去掉 project 字段

**步骤 4：前端**
- Zustand store 加 `currentProject`、`projectList`
- ProjectPanel 加项目列表、新建/删除按钮
- AnalyzePanel 监听 `currentProject` 切换 → 清空 → 加载快照
- `replyPending` 时禁止切项目

**步骤 5：报告页**
- 报告 URL 改为 `/api/reports/{project_name}/latest`

**步骤 6：清理**
- 删 `_shared_orchestrator`、`_analysis_busy_lock` 等全局变量
- 更新测试中的引用

---

## 六、设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 内存模型 | dict 存所有项目 vs 单例当前项目 | **单例** | 磁盘加载 <100ms，更简单，避免多项目并发 |
| 前端缓存 | 缓存所有项目状态 vs 每次重新加载 | **不缓存** | 磁盘加载够快，省前端复杂度 |
| 切项目时分析中 | 禁止 vs 自动暂停 | **禁止** | 保证当前项目稳定，单次 LLM 调用很快完成 |
| 旧项目兼容 | 自动迁移 vs 不需要 | **不需要** | 老项目数据直接删除，从零开始 |
| WS 协议 | 所有命令带 project vs 只切项目带 | **只切项目带** | 减少冗余，当前项目是隐式上下文 |

## 七、风险评估

| 风险 | 缓解 |
|------|------|
| 项目切换时磁盘写入失败 → 状态丢失 | switch 前 save_state() 失败时拒绝切换 |
| 重连后恢复哪个项目 | 扫描 projects/，找有 current_run_id 且最近修改的 |
| 项目文件夹被手动删除 | ProjectManager 启动时扫描，不存在的项目从列表中移除 |
| 前端状态切换闪烁 | 清空面板瞬间 (<100ms) + 快照立即渲染 |

---

## 七、不做的

- 不改变 LLM 对话模型（prompt/工具/session 不变）
- 不改变单次分析的流程（4 阶段不变）
- 不改变通道模型（信息通道/控制通道不变，参考 `docs/CHANNEL.md`）
- PDF 导出（后续版本）
