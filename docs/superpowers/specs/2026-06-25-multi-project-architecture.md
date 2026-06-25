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
| 多项目支持 | 单 `_shared_orchestrator` | `_project_sessions: dict` |

---

## 二、后端：ProjectManager

### 核心类

```python
class ProjectManager:
    """管理所有项目的生命周期"""

    _sessions: dict[str, Orchestrator]  # {project_name: orchestrator}

    def get_or_create(self, project_name: str) -> Orchestrator:
        """获取项目 orchestrator。
        1. 内存有 → 返回
        2. 内存无 → 从磁盘恢复（最新 orch_state.json）
        3. 磁盘无 → 创建新 orchestrator（需要先上传数据）
        """

    def run_analysis(self, project_name: str, data_path: str, query: str):
        """为项目启动新分析。
        创建 run 目录 → 写入 project.json → orchestrator.run()
        """

    def respond(self, project_name: str, text: str) -> dict:
        """处理用户回复。找到对应项目 orchestrator → respond()"""

    def get_snapshot(self, project_name: str) -> dict:
        """返回项目当前状态快照，供前端恢复"""

    def cancel_respond(self, project_name: str):
        """取消当前项目的 respond 处理"""

    def save_project(self, project_name: str):
        """保存项目状态到磁盘"""
```

### 替换现有全局变量

| 现有 | 替换为 |
|------|--------|
| `_shared_orchestrator` | `_project_manager.sessions[project_name]` |
| `_analysis_in_progress` | `_project_manager.sessions[project_name]._analysis_busy` |
| `orch.run()` | `_project_manager.run_analysis(project_name, ...)` |
| `orch.respond()` | `_project_manager.respond(project_name, text)` |

### 初始化流程

```
应用启动
  → ProjectManager 初始化
  → 扫描 projects/ 目录，找所有 project.json
  → 找到有 current_run_id 的项目 → 恢复 orchestrator
  → 前端连接 → 推送项目列表 + 上次打开的项目快照
```

---

## 三、WS 协议扩展

每个命令加 `project` 字段：

```json
// 新增项目
{"cmd": "create_project", "project": "新项目"}
// 切换项目
{"cmd": "switch_project", "project": "test0625"}
// 分析
{"cmd": "analyze", "project": "test0625", "payload": {"data_path": "...", "query": "..."}}
// 回复
{"cmd": "respond", "project": "test0625", "payload": {"text": "Inc1是收入"}}
// 取消回复
{"cmd": "cancel_respond", "project": "test0625"}
// 取消分析
{"cmd": "cancel_analysis", "project": "test0625"}
// 获取项目列表
{"cmd": "list_projects"}
// 上传数据
{"cmd": "upload_data", "project": "test0625", "payload": {...}}
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

## 四、前端：多项目状态管理

### Zustand Store

```typescript
interface WorkspaceState {
  // 全局
  currentProject: string | null;
  projectList: string[];
  connectionStatus: ConnectionStatus;

  // 每个项目独立状态
  projectStates: Record<string, ProjectState>;
}

interface ProjectState {
  dataPath: string;
  query: string;
  messages: ConvoMessage[];
  phase: string;
  reportUrl: string | null;
  waitingAgent: string | null;
  gateOpen: boolean;
  // ... 其他项目级状态
}
```

### 项目切换流程

```
用户点击项目B
  ↓
1. 保存项目A状态到 projectStates["A"]
2. 设置 currentProject = "B"
3. 检查 projectStates["B"] 是否有缓存
   ├─ 有 → 直接渲染
   └─ 无 → 发送 {"cmd": "switch_project", "project": "B"}
          → 接收 state_snapshot → 恢复 → 渲染
```

### UI 改动

| 组件 | 改动 |
|------|------|
| ProjectPanel | 项目列表 + 新建/删除项目 |
| AnalyzePanel | 监听 currentProject 切换 → 自动恢复 |
| ReportPanel | 显示当前项目的报告 |
| 标题栏 | 显示当前项目名 |

---

## 五、实现顺序

| 步骤 | 内容 | 文件 | 依赖 |
|------|------|------|------|
| 1 | 项目文件夹结构化 | orchestrator.py（save_state 写 project.json + memory.json）| 无 |
| 2 | ProjectManager 类 | 新建 `hagoku/manager/project_manager.py` | 步骤 1 |
| 3 | ws_handler 改 project 参数 | ws_handler.py（所有 cmd 加 project）| 步骤 2 |
| 4 | 前端多项目 Store | workspace.ts + AnalyzePanel.tsx | 步骤 3 |
| 5 | 项目切换功能 | ProjectPanel.tsx + AnalyzePanel.tsx | 步骤 4 |
| 6 | 报告页项目感知 | ReportPanel.tsx | 步骤 5 |
| 7 | 清理全局单例 | 全局变量 → ProjectManager 属性 | 步骤 2 |

---

## 六、风险评估

| 风险 | 概率 | 缓解 |
|------|------|------|
| 项目切换时丢数据 | 低 | 切换前 save_state()，恢复路径已验证 |
| 两项目同时分析 | 低 | 单用户场景不会，多 WS 连接由并发锁保护 |
| 旧项目数据格式不兼容 | 中 | project.json 不存在时回退到只读模式（runs 目录仍可访问）|
| 前端状态切换闪烁 | 低 | projectStates 缓存减少请求 |

---

## 七、不做的

- 不改变 LLM 对话模型（prompt/工具/session 不变）
- 不改变单次分析的流程（4 阶段不变）
- 不改变通道模型（信息通道/控制通道不变，参考 `docs/CHANNEL.md`）
- PDF 导出（后续版本）
