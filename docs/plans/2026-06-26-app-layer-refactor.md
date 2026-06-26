# 多项目架构重构 — App 层引入方案

> 状态：评估完成，待执行
> 日期：2026-06-26

## 背景

2026-06-25 引入多项目架构，但落地为补丁拼装：

- 两个 `ProjectManager` 类互不相通（`manager/pm.py` vs `storage/pm.py`）
- 三种项目创建路径，三种目录结构（REST API / WS / CLI 各自操作文件系统）
- 层依赖反转（`manager/pm.py` 从 `api/ws_handler.py` 导入）
- 6 个模块级全局变量散布在 `ws_handler.py`，无生命周期管理
- REST API 删除项目绕过安全校验（`shutil.rmtree` 直接操作）
- 多处 `except: pass` 违反铁律 7

## 方案：引入 App 层

```
API (server.py / ws_handler.py)     ← 只做 parse → delegate → format
  ↓
App (hagoku/app.py)                 ← 新增，进程级单例
  ↓
Repository (hagoku/repository/)     ← 合并两个 PM，统一 project.json
  ↓
Domain (Orchestrator / Session)     ← 不变，通道核心不动
```

### 新文件

| 文件 | 职责 |
|------|------|
| `hagoku/app.py` | `HaGoKuApp` — 进程级单例，持有 Repository + 当前 Orch，暴露 `get_orch()` / `switch_project()` / `build_snapshot()` / `is_busy()` |
| `hagoku/repository/__init__.py` | 空 |
| `hagoku/repository/project.py` | `ProjectRepository` — 纯文件 I/O：项目 CRUD + `_safe_rmtree` + 元数据读写 + 项目列表。不依赖 Orchestrator |

### 改动文件

| 文件 | 动作 |
|------|------|
| `hagoku/api/server.py` | lifespan 创建 App → `app.state`；所有端点 delegate；删直接文件操作 |
| `hagoku/api/ws_handler.py` | 删 6 个全局变量；从 `app.state` 取 App；`_build_state_snapshot` 移走 |
| `hagoku/manager/project_manager.py` | 方法迁入 Repository 后降级为存根（或删除） |
| `hagoku/storage/project_manager.py` | 同上 |
| `hagoku/manager/orchestrator.py` | 删 `self.project_mgr`（未使用）；删 `_log_channel` 的 `except:pass` |
| `hagoku/cli.py` | 6 处 import 改为 `ProjectRepository` |
| `tests/` | 适配新的 import 路径和 App 实例 |

### 不变文件（通道核心）

| 文件 | 原因 |
|------|------|
| `hagoku/channel.py` | `build_messages()` 唯一入口 |
| `hagoku/context/session.py` | 消息会话管理 |
| `hagoku/agents/agent.py` | `run_step()` 工具循环 |
| `hagoku/manager/llm_dispatch/reply_handlers.py` | `respond()` 通道 |
| `hagoku/tools/` | 工具注册表 |

## 迁移步骤

### Step 1: 新建 ProjectRepository
- 创建 `hagoku/repository/project.py`
- 纯文件 I/O：项目 CRUD + `_safe_rmtree` + 元数据读写（`project.json` + 兼容读旧 `project.yaml`）+ 项目列表
- **不**依赖 Orchestrator，不涉及 orch 生命周期
- 不删旧文件
- 跑 `pytest tests/ -q`（验证旧代码未破坏）

### Step 2: 新建 HaGoKuApp
- 创建 `hagoku/app.py`
- `HaGoKuApp` 持有 `ProjectRepository` + `_active_orch`
- `get_orch()` / `switch_project()` / `build_snapshot()` / `is_busy()` / `_load_project()`
- Orch 生命周期归 App，文件 I/O delegate 到 Repository
- 跑 `pytest tests/ -q`

### Step 3: 切 API 层
- `server.py` lifespan 创建 `HaGoKuApp` → `app.state.hagoku_app`
- 所有端点从 `request.app.state` 取 App，delegate 方法调用
- `ws_handler.py` 删全局变量，从 `request.app.state` 取 App
- `_build_state_snapshot` 改为 `app.build_snapshot()`
- **修复 `_run_analysis_task` 用 `get_orchestrator()` 替代直调 `_shared_orchestrator`**（`ws_handler.py:110,116`）
- 修 `_log_channel` 的 `except:pass`（`orchestrator.py:81`）
- 跑 `pytest tests/ -q` + `bash scripts/ci/self_check.sh`

### Step 4: 切 CLI + 清理
- `cli.py` 6 处 import 改为 `ProjectRepository`
- 删 `manager/pm.py`、`storage/pm.py`（或保留为空存根）
- 跑 `pytest tests/ -q` + `bash scripts/ci/self_check.sh`

## 不在此方案中的

- 死代码清理（`_run_analysis`、空 property、`_STAGE_HANDLERS`）— 另案处理
- 铁律 7 违规修复（`except:pass`）— 将在 Step 3/4 中顺带修复
- 前端改动 — 无需改动

## 检验标准

每个 Step 完成后：
1. `pytest tests/ -q` 全绿
2. `bash scripts/ci/self_check.sh` 全绿
3. 通道核心（`build_messages` → `run_step` → `respond` → 流式）未被修改
