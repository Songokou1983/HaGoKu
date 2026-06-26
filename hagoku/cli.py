"""HaGoKu Studio CLI — 命令行入口"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from .config import HaGoKuConfig

# 可用的演示数据集
DEMO_DATASETS = {
    "ad_campaign": {
        "name": "广告投放数据",
        "file": "demo_ad_campaign.csv",
        "desc": "百度/抖音/微信 3 渠道的广告投放效果（展示/点击/消费/收入）",
        "suggested_query": "哪个广告渠道的 ROI 最高？各渠道转化率有何差异？",
    },
    "conversion": {
        "name": "转化漏斗数据",
        "file": "demo_conversion.csv",
        "desc": "从访问→注册→加购→下单→付款的全链路转化漏斗",
        "suggested_query": "分析各渠道的转化漏斗，哪个环节流失最严重？",
    },
    "user_cohort": {
        "name": "用户队列数据",
        "file": "demo_user_cohort.csv",
        "desc": "用户基本信息、渠道来源、消费行为、会员等级",
        "suggested_query": "各渠道用户质量和价值有什么差异？哪些是高价值用户群？",
    },
}


def _get_demo_path(name: str) -> Path | None:
    """解析 demo 数据集名，返回对应的文件路径（支持包内/本地两种模式）"""
    if name not in DEMO_DATASETS:
        return None
    filename = DEMO_DATASETS[name]["file"]

    # 尝试从源码路径加载（开发模式）
    # __file__ = hagoku/cli.py → 项目根 = 上2级
    this_file = Path(__file__)
    project_root = this_file.parent.parent
    local_demo = project_root / "examples" / filename
    if local_demo.exists():
        return local_demo

    # 尝试从包内路径加载（wheel 安装后）
    try:
        import hagoku
        # hagoku.__file__ = hagoku/__init__.py
        pkg_proj = Path(hagoku.__file__).parent.parent  # = 项目根/
        pkg_demo = pkg_proj / "examples" / filename
        if pkg_demo.exists():
            return pkg_demo
    except Exception:
        pass

    return None


WELCOME_SCREEN = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   HaGoKu Studio  用数学的力量，挖出数据背后真正的信息             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝

🚀 快速开始：
   hagoku demo                            # 查看示例数据
   hagoku run --demo ad_campaign -q "哪个渠道roi最高"
   hagoku run --demo conversion -q "分析转化漏斗"

📂 完整命令：
   hagoku run <file> -q "问题"          # 运行分析
   hagoku profile <file>               # 数据画像
   hagoku project create <名称>         # 创建项目
   hagoku doctor                         # 检查系统状态
   hagoku-ui                            # 启动 Web UI

💡 示例数据（无需准备，直接体验）：
   ad_campaign   广告投放数据（百度/抖音/微信）
   conversion   转化漏斗数据
   user_cohort  用户队列数据

文档：https://github.com/hagoku/hagoku
"""


@click.group()
@click.version_option(package_name="hagoku")
def cli() -> None:
    """HaGoKu Studio — 用数学的力量，挖出数据背后真正的信息"""
    pass


@cli.command()
@click.argument("data_path", type=click.Path(exists=True), required=False)
@click.option("--query", "-q", default="", help="分析问题")
@click.option("--demo", "-D", default=None,
              type=click.Choice(list(DEMO_DATASETS.keys())),
              help="使用内置演示数据集（可简写为 -D ad_campaign）")
@click.option("--project", "-p", default=None, help="项目名")
@click.option("--output-dir", "-o", default=None, help="输出目录")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["html", "md", "json"]),
              help="输出格式（可多次指定）")
@click.option("--template", "-t", default=None,
              type=click.Choice(["default", "academic", "brief", "business_analysis", "ab_test", "executive_brief", "data_audit"]),
              help="报告模板")
@click.option("--resume", is_flag=True, help="从上次断点继续分析")
@click.option("--progress", "progress_path", default=None, type=click.Path(exists=True),
              help="外部 progress.yaml 路径")
@click.option("--verbosity", "-v", default="normal",
              type=click.Choice(["quiet", "normal", "verbose"]),
              help="终端输出详细度")
@click.option("--interactive", "-i", is_flag=True,
              help="交互模式：分析完成后继续等待你的调整指令")
def run(
    data_path: str | None,
    query: str,
    demo: str | None,
    project: str | None,
    output_dir: str | None,
    formats: tuple[str, ...],
    template: str | None,
    resume: bool,
    progress_path: str | None,
    verbosity: str,
    interactive: bool = False,
) -> None:
    """运行完整分析流程

    示例：
        hagoku run data.csv -q "哪个渠道效果最好"
        hagoku run --demo ad_campaign -q "哪个渠道roi最高"
        hagoku run -D conversion -q "分析转化漏斗"
    """
    from .manager.orchestrator import Orchestrator
    from .observability.display import TerminalDisplay

    # --demo 优先：从内置数据集解析路径
    if demo:
        resolved = _get_demo_path(demo)
        if resolved is None:
            click.echo(f"❌ 找不到演示数据集: {demo}", err=True)
            click.echo("   使用 `hagoku demo` 查看可用的演示数据集")
            raise SystemExit(1)
        data_path = str(resolved)
        ds_info = DEMO_DATASETS[demo]
        if verbosity != "quiet":
            click.echo(f"📊 演示数据: {ds_info['name']} ({ds_info['desc']})")
            if not query:
                query = ds_info["suggested_query"]
                click.echo(f"   自动推荐问题: {query}")
    elif not data_path:
        click.echo("❌ 请提供数据文件路径，或使用 --demo <数据集> 选择演示数据", err=True)
        click.echo("   可用演示数据: " + " ".join(DEMO_DATASETS.keys()))
        click.echo("   示例: hagoku run --demo ad_campaign -q \"哪个渠道roi最高\"")
        raise SystemExit(1)

    # 加载配置
    config = HaGoKuConfig.load()

    # 创建编排器
    orch = Orchestrator(config)

    # 替换显示为用户指定的详细度
    orch.event_bus.unsubscribe(orch.display)
    orch.display = TerminalDisplay(verbosity=verbosity)
    orch.event_bus.subscribe(orch.display)

    # 执行分析
    format_list = list(formats) if formats else None
    try:
        result = orch.run(
            data_path=data_path,
            query=query,
            project_name=project,
            output_dir=output_dir,
            formats=format_list,
            template=template,
            resume=resume,
            progress_path=progress_path,
        )
    except FileNotFoundError:
        click.echo("\n❌ 数据文件未找到", err=True)
        click.echo("   请检查文件路径是否正确，或确认文件扩展名是 CSV/Excel/JSON/Parquet 之一", err=True)
        raise SystemExit(1)
    except RuntimeError as e:
        click.echo(f"\n❌ 分析过程遇到问题: {e}", err=True)
        if verbosity == "verbose":
            import traceback
            traceback.print_exc()
        raise SystemExit(1)
    except Exception:
        click.echo("\n❌ 分析过程中出现意外错误", err=True)
        click.echo("   可能原因：数据格式异常、LLM 服务不可用、配置错误", err=True)
        click.echo("   提示：使用 -v verbose 查看详细错误信息", err=True)
        if verbosity == "verbose":
            import traceback
            traceback.print_exc()
        raise SystemExit(1)

    if result["status"] == "completed":
        if verbosity != "quiet":
            click.echo(f"\n✅ 分析完成！报告: {result['output_path']}")

        # 交互模式：进入 refinement REPL
        if interactive:
            _run_refinement_loop(
                data_path=data_path,
                project_name=result.get("project"),
                result=result,
                orch=orch,
                verbosity=verbosity,
            )
    elif result["status"] == "guardrails_blocked":
        if verbosity != "quiet":
            click.echo("\n⚠️ 统计护栏（强制级）未通过，已跳过正式报告生成。", err=False)
            click.echo(f"   说明文件: {result.get('output_path', '')}")
    else:
        click.echo("\n❌ 分析未能完成", err=True)
        click.echo("   请检查数据质量，或使用 -v verbose 查看详细信息", err=True)
        raise SystemExit(1)


@cli.command(name="demo")
@click.argument("dataset", required=False,
                type=click.Choice(list(DEMO_DATASETS.keys()) + ["list"]))
@click.option("--query", "-q", default=None, help="分析问题（可选，留空使用推荐问题）")
def demo_cmd(dataset: str | None, query: str | None) -> None:
    """查看或运行内置演示数据集

    示例：
        hagoku demo                           # 列出所有演示数据集
        hagoku demo ad_campaign               # 查看广告投放数据集详情
        hagoku demo ad_campaign -q "哪个渠道roi最高"  # 直接运行分析
    """
    if dataset is None or dataset == "list":
        _list_demos()
        return

    # 运行指定演示数据集
    ds_info = DEMO_DATASETS[dataset]
    resolved = _get_demo_path(dataset)
    if resolved is None:
        click.echo(f"❌ 找不到演示数据集: {dataset}", err=True)
        raise SystemExit(1)

    # 用 demo 数据替换 data_path，重新调用 run 逻辑
    from .manager.orchestrator import Orchestrator
    from .observability.display import TerminalDisplay

    config = HaGoKuConfig.load()

    effective_query = query or ds_info["suggested_query"]
    if not query:
        click.echo(f"📊 演示数据: {ds_info['name']}")
        click.echo(f"   {ds_info['desc']}")
        click.echo(f"   自动使用推荐问题: {effective_query}")
    else:
        click.echo(f"📊 演示数据: {ds_info['name']}")

    orch = Orchestrator(config)
    orch.event_bus.unsubscribe(orch.display)
    orch.display = TerminalDisplay(verbosity="normal")
    orch.event_bus.subscribe(orch.display)

    try:
        result = orch.run(
            data_path=str(resolved),
            query=effective_query,
        )
    except Exception:
        click.echo("❌ 分析过程中出现意外错误", err=True)
        raise SystemExit(1)

    if result["status"] == "completed":
        click.echo(f"\n✅ 报告: {result['output_path']}")
    elif result["status"] == "guardrails_blocked":
        click.echo("\n⚠️ 统计护栏（强制级）未通过，已跳过正式报告。", err=False)
        click.echo(f"   说明文件: {result.get('output_path', '')}")
    else:
        click.echo("❌ 分析未能完成", err=True)
        raise SystemExit(1)


def _list_demos() -> None:
    """列出所有可用的演示数据集"""
    click.echo("📊 HaGoKu Studio 内置演示数据集\n")
    for key, info in DEMO_DATASETS.items():
        path = _get_demo_path(key)
        status = "✅" if path else "❌"
        click.echo(f"  {status} {key}")
        click.echo(f"     {info['name']}: {info['desc']}")
        click.echo(f"     推荐问题: {info['suggested_query']}")
        if path:
            click.echo(f"     文件: {path}")
        click.echo()

    click.echo("用法:")
    click.echo("  hagoku demo ad_campaign              # 查看数据详情")
    click.echo("  hagoku demo ad_campaign -q \"哪个渠道效果最好\"  # 运行分析")
    click.echo("  hagoku run --demo ad_campaign -q \"哪个渠道效果最好\"  # 同上")


@cli.command()
@click.argument("data_path", type=click.Path(exists=True))
def profile(data_path: str) -> None:
    """生成数据画像"""
    from .tools.data_io import load_data
    from .tools.profiling import generate_profile

    df = load_data(data_path)
    p = generate_profile(df)

    click.echo(f"📊 数据画像: {data_path}")
    click.echo(f"   行数: {p['n_rows']}")
    click.echo(f"   列数: {p['n_cols']}")
    click.echo(f"   质量: {p['quality_score']}")
    click.echo(f"   重复率: {p['duplicate_rate']:.1%}")

    missing = p["missing_summary"]
    if missing["columns_with_nulls"] > 0:
        click.echo(f"\n   ⚠️ 缺失值 ({missing['columns_with_nulls']} 列):")
        for col, detail in missing["column_details"].items():
            click.echo(f"     • {col}: {detail['count']} ({detail['rate']:.1%})")

    click.echo("\n📋 列信息:")
    for col, info in p["columns"].items():
        type_icon = {"numeric": "🔢", "categorical": "🏷️", "datetime": "📅",
                     "boolean": "✓", "id": "🔑", "unknown": "❓"}.get(info["inferred_type"], "•")
        click.echo(f"   {type_icon} {col}: {info['inferred_type']} "
                   f"(缺失 {info['null_rate']:.1%}, 唯一 {info['unique_count']})")


@cli.command()
def projects() -> None:
    """列出所有项目"""
    from .storage.database import HaGoKuDB

    config = HaGoKuConfig.load()
    db = HaGoKuDB.get_instance(config.work_dir / "hagoku.db")
    projs = db.list_projects()

    if not projs:
        click.echo("暂无项目。使用 `hagoku run` 开始第一个分析。")
        return

    for p in projs:
        click.echo(f"📁 {p['id']} ({p.get('created_at', 'N/A')[:10]})")
        if p.get("description"):
            click.echo(f"   {p['description']}")


@cli.command()
@click.argument("project_name")
def history(project_name: str) -> None:
    """查看项目运行历史"""
    from .storage.database import HaGoKuDB

    config = HaGoKuConfig.load()
    db = HaGoKuDB.get_instance(config.work_dir / "hagoku.db")
    runs = db.get_run_history(project_name)

    if not runs:
        click.echo(f"项目 '{project_name}' 暂无运行记录。")
        return

    click.echo(f"📋 项目 '{project_name}' 运行历史:")
    for r in runs:
        status_icon = {"completed": "✅", "running": "🔄", "failed": "❌"}.get(r["status"], "❓")
        duration = f"{r.get('duration_ms', 0) / 1000:.1f}s" if r.get("duration_ms") else "..."
        click.echo(f"  {status_icon} {r['id']} | {r.get('query', 'N/A')[:40]} | {r['status']} | {duration}")


@cli.command(name="config")
@click.option("--reset", is_flag=True, help="重置配置为默认值")
def config_cmd(reset: bool) -> None:
    """查看/管理配置"""
    if reset:
        config_path = Path.home() / ".hagoku" / "config.yaml"
        if config_path.exists():
            config_path.unlink()
            click.echo("✅ 配置已重置为默认值")
        else:
            click.echo("配置已是默认值")
        return

    config = HaGoKuConfig.load()
    click.echo("⚙️ HaGoKu Studio 配置:")
    click.echo(f"   LLM: {config.llm.model} @ {config.llm.base_url}")
    click.echo(f"   工作目录: {config.work_dir}")
    click.echo(f"   输出格式: {', '.join(config.output.formats)}")


@cli.command(name="methods")
@click.option("--tag", "-t", default=None, help="按关注点过滤 (理解字段/评估清洗/跑统计/写报告)")
def list_methods(tag: str | None) -> None:
    """查看所有可用的 Agent 工具

    HaGoKu Studio 的工具按关注点分类：

    探查(4)     get_column_stats, get_sample_rows, list_columns, group_stats
    字段(1)     set_columns
    清洗(2)     detect_outliers, detect_missing_pattern
    统计(3)     run_statistical_test, check_test_assumptions, correct_multiple_comparisons
    分析(2)     submit_assessment, submit_findings
    可视化(1)   create_plot
    流程(1)     ask_user
    """
    from .tools.registry import agent_tools

    tools = agent_tools.list_for_agent("")
    click.echo("📊 HaGoKu Studio Agent 工具")
    click.echo(f"   共 {len(tools)} 个注册工具")
    click.echo()

    if tag:
        tools = [t for t in tools if tag in (t.phase_tag or [])]
        click.echo(f"  关注点 [{tag}] ({len(tools)} 个):")
    else:
        # 按关注点分组
        from collections import defaultdict
        by_phase = defaultdict(list)
        for t in tools:
            for ph in (t.phase_tag or []):
                if ph not in by_phase:
                    by_phase[ph] = []
                by_phase[ph].append(t.name)

        tag_groups = {
            "理解字段": "🔍 理解字段",
            "评估清洗": "🧹 评估清洗",
            "跑统计": "📊 跑统计",
            "写报告": "📝 写报告",
        }
        for phase, label in tag_groups.items():
            names = by_phase.get(phase, [])
            if names:
                click.echo(f"  {label} ({len(names)}):")
                for n in sorted(names):
                    click.echo(f"    • {n}")

        click.echo()

    for t in sorted(tools, key=lambda t: t.name):
        desc = t.description.split("\n")[0][:80]
        click.echo(f"   • {t.name:<30} {desc}")

    click.echo()


@cli.group(name="doctor", invoke_without_command=True)
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """HaGoKu Doctor — 系统健康检查与资产审计

    \b
    示例：
        hagoku doctor                    # 完整健康检查
        hagoku doctor health             # 同上
        hagoku doctor audit-methods      # 审知识库
        hagoku doctor audit-tools        # 审工具箱
        hagoku doctor tool-gate          # CI 守门检查
    """
    if ctx.invoked_subcommand is None:
        # 无子命令时执行默认健康检查
        _run_doctor_health()


@doctor_cmd.command(name="health")
def doctor_health_cmd() -> None:
    """系统健康检查（LLM 连接、依赖库）"""
    _run_doctor_health()


def _run_doctor_health() -> None:
    from .tools.health import check_system, format_health_report

    click.echo("🔍 HaGoKu Studio 系统健康检查...")
    results = check_system()
    click.echo(format_health_report(results))

    # 如果 LLM 不可用，给出配置提示
    llm_result = next((r for r in results if r.name == "LLM 服务"), None)
    if llm_result and not llm_result.ok:
        click.echo()
        click.echo("💡 快速配置 LLM:")
        click.echo("   hagoku config                    # 查看当前配置")
        click.echo("   # 或设置环境变量:")
        click.echo("   export HAGOKYU_LLM_BASE_URL=<你的 LLM 地址>")


@doctor_cmd.command(name="audit-methods")
def doctor_audit_methods_cmd() -> None:
    """审计学术方法库（MethodCurator）"""
    click.echo("🔍 MethodCurator — 审计学术方法库...")
    try:
        from .agents.method_curator.agent import run_method_audit
        path = run_method_audit()
        click.echo(f"✅ 审计完成: {path}")
    except Exception as e:
        click.echo(f"❌ 审计失败: {e}", err=True)
        raise SystemExit(1)


@doctor_cmd.command(name="audit-tools")
def doctor_audit_tools_cmd() -> None:
    """审计工具箱（ToolCurator）"""
    click.echo("🔍 ToolCurator — 审计工具箱...")
    try:
        from .agents.tool_curator.agent import run_tool_audit
        path = run_tool_audit()
        click.echo(f"✅ 审计完成: {path}")
    except Exception as e:
        click.echo(f"❌ 审计失败: {e}", err=True)
        raise SystemExit(1)


@doctor_cmd.command(name="tool-gate")
def doctor_tool_gate_cmd() -> None:
    """CI 确定性守门检查（G1-G4）"""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "ci" / "tool_gate.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=False,
    )
    raise SystemExit(result.returncode)


@cli.command(name="desktop")
def desktop_cmd() -> None:
    """启动 HaGoKu Desktop 桌面应用"""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "desktop" / "start.sh"
    if not script.exists():
        click.echo("❌ 桌面应用未安装。请先运行: cd desktop && npm install", err=True)
        raise SystemExit(1)
    click.echo("🖥️ 启动 HaGoKu Studio Desktop...")
    result = subprocess.run(["bash", str(script)], cwd=script.parent)
    raise SystemExit(result.returncode)


@cli.command()
def guardrails() -> None:
    """查看统计护栏规则"""
    from .guardrails.statistical import StatisticalGuardrails

    g = StatisticalGuardrails()

    click.echo("🛡️ 统计护栏规则:")
    click.echo()
    click.echo("🚫 强制级（违规 = 阻止输出）:")
    for rule in g.mandatory_rules:
        click.echo(f"   • {rule.rule_name}")

    click.echo()
    click.echo("⚠️ 警告级（违规 = 标注警告）:")
    for rule in g.warning_rules:
        click.echo(f"   • {rule.rule_name}")

    click.echo()
    click.echo("💡 提示级（违规 = 建议）:")
    for rule in g.suggestion_rules:
        click.echo(f"   • {rule.rule_name}")


@cli.command()
@click.argument("run_id")
@click.option("--agent", "-a", default=None, help="只回放指定 agent 的事件")
@click.option("--verbose", "-v", is_flag=True, help="显示完整事件数据")
def replay(run_id: str, agent: str | None, verbose: bool) -> None:
    """回放分析过程"""
    import json

    from .config import HaGoKuConfig

    config = HaGoKuConfig.load()
    projects_dir = config.output.project_dir

    if not projects_dir.exists():
        click.echo(f"运行 '{run_id}' 不存在或无事件日志（项目目录尚未创建）。")
        return

    # 查找 run 目录
    events_path = None
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        # 运行目录可能在 project_dir/ 下，也可能在 project_dir/runs/ 下
        runs_dir = project_dir / "runs"
        search_dirs = [project_dir]
        if runs_dir.is_dir():
            search_dirs.append(runs_dir)
        for search_dir in search_dirs:
            for run_dir in search_dir.iterdir():
                if run_dir.name == run_id and run_dir.is_dir():
                    candidate = run_dir / "events.jsonl"
                    if candidate.exists():
                        events_path = candidate
                        break
            if events_path:
                break
        if events_path:
            break

    if events_path is None:
        click.echo(f"运行 '{run_id}' 不存在或无事件日志。")
        return

    # 读取事件
    events = []
    with open(events_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    # 过滤
    if agent:
        events = [e for e in events if e.get("agent") == agent]

    if not events:
        click.echo("无匹配事件。")
        return

    # 显示
    agent_colors = {
        "Manager": "\033[35m",
        "Scout": "\033[36m",
        "Cleaner": "\033[33m",
        "Analyst": "\033[34m",
        "Reporter": "\033[32m",
    }
    reset = "\033[0m"

    click.echo(f"📋 回放运行 {run_id} ({len(events)} 个事件)")
    click.echo("=" * 60)

    for event in events:
        evt_type = event.get("event_type", "?")
        evt_agent = event.get("agent", "?")
        timestamp = event.get("timestamp", "")[11:19]  # HH:MM:SS
        data = event.get("data", {})

        color = agent_colors.get(evt_agent, "")

        if evt_type == "agent_thinking":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 💭 {data.get('thought', '')[:100]}")
        elif evt_type == "tool_called":
            tool = data.get("tool", "?")
            args = data.get("args_summary", "")
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 🔧 {tool}({args})")
        elif evt_type == "tool_result":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} ✅ {data.get('summary', '')[:100]}")
        elif evt_type == "tool_error":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} ❌ {data.get('error', '')[:100]}")
        elif evt_type == "agent_started":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 🚀 开始")
        elif evt_type == "agent_completed":
            duration = data.get("duration", "?")
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} ✅ 完成 ({duration})")
        elif evt_type == "agent_failed":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} ❌ 失败: {data.get('error', '')[:100]}")
        elif evt_type == "quality_check":
            verdict = data.get("verdict", "?")
            detail = data.get("detail", "")
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 🛡️ 质检: {verdict} {detail}")
        elif evt_type == "run_started":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 🏁 开始运行: {data.get('query', '')[:60]}")
        elif evt_type == "run_completed":
            click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} 🏁 运行完成: {data.get('duration', '?')} → {data.get('output_path', '')}")
        else:
            if verbose:
                click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} [{evt_type}] {json.dumps(data, ensure_ascii=False)[:120]}")
            else:
                click.echo(f"  {color}{timestamp} [{evt_agent}]{reset} [{evt_type}]")


@cli.group(name="project")
def project_cmd() -> None:
    """项目管理：立项、添加数据、查看详情

    项目是独立的分析工作区，每个项目有：
      - input/  原始数据文件
      - process/ 清洗后数据、中间结果
      - output/ 报告、可视化

    工作流：
      hagoku project create "Q1销售分析"
      hagoku project add "Q1销售分析" ~/data/sales.csv
      hagoku project run "Q1销售分析" -q "哪个渠道效果最好"
    """
    pass


@project_cmd.command(name="create")
@click.argument("name")
@click.option("--desc", "-d", default="", help="项目描述")
def project_create(name: str, desc: str) -> None:
    """创建新项目（立项）"""
    from .config import HaGoKuConfig
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)

    try:
        info = pm.create(name, description=desc)
        click.echo(f"✅ 项目创建成功: {info.name}")
        click.echo(f"   目录: {info.project_dir}")
        click.echo("   结构: input/  process/  output/")
        if desc:
            click.echo(f"   描述: {desc}")
    except FileExistsError as e:
        click.echo(f"❌ {e}", err=True)
        raise SystemExit(1)


@project_cmd.command(name="add")
@click.argument("project")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--link", "-l", is_flag=True, help="用符号链接而非复制文件")
def project_add(project: str, file_path: str, link: bool) -> None:
    """向项目添加数据文件"""
    from .config import HaGoKuConfig
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)

    try:
        info = pm.add_data(project, Path(file_path), copy=not link)
        proj_info = pm.info(project)
        mode = "链接" if link else "复制"
        click.echo(f"✅ {mode}成功: {info.name} ({info.size_kb:.1f} KB)")
        if proj_info is not None:
            click.echo(f"   路径: {proj_info.project_dir / info.path}")
    except FileNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        raise SystemExit(1)


@project_cmd.command(name="list")
def project_list() -> None:
    """列出所有项目"""
    from .config import HaGoKuConfig
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)
    projects = pm.list()

    if not projects:
        click.echo("暂无项目。")
        click.echo("  创建: hagoku project create <项目名>")
        return

    click.echo(f"📁 共 {len(projects)} 个项目:\n")
    for p in projects:
        date_str = p.created_at.strftime("%Y-%m-%d")
        run_info = f" | {p.run_count}次运行" if p.run_count > 0 else ""
        last_str = f"（最近 {p.last_run.strftime('%m-%d %H:%M')}" if p.last_run else ""
        data_count = len(p.data_files)
        data_info = f" | 📄 {data_count}个数据文件" if data_count > 0 else ""
        click.echo(f"  📁 {p.name}  {date_str}{run_info}{last_str}{data_info}")
        if p.description:
            click.echo(f"      {p.description}")


@project_cmd.command(name="info")
@click.argument("project")
def project_info(project: str) -> None:
    """查看项目详情"""
    from .config import HaGoKuConfig
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)
    info = pm.info(project)

    if info is None:
        click.echo(f"❌ 项目不存在: {project}", err=True)
        raise SystemExit(1)

    click.echo(f"📁 项目: {info.name}")
    click.echo(f"   创建: {info.created_at.strftime('%Y-%m-%d %H:%M')}")
    if info.description:
        click.echo(f"   描述: {info.description}")
    click.echo(f"   目录: {info.project_dir}")
    click.echo(f"   运行: {info.run_count}次" + (
        f"（最近 {info.last_run.strftime('%Y-%m-%d %H:%M')}）" if info.last_run else ""))
    click.echo()

    if info.data_files:
        click.echo(f"  📄 输入文件 ({len(info.data_files)}):")
        for f in info.data_files:
            added = f.added_at.strftime("%m-%d %H:%M")
            click.echo(f"    • {f.name}  {f.size_kb:.1f} KB  添加于 {added}")
    else:
        click.echo("  📄 输入文件: （暂无，添加: hagoku project add）")

    click.echo()

    if info.process_files:
        click.echo(f"  ⚙️ 过程文件 ({len(info.process_files)}):")
        for f in info.process_files:
            click.echo(f"    • {f.name}  {f.size_kb:.1f} KB")
    else:
        click.echo("  ⚙️ 过程文件: （暂无，分析后自动生成）")


@project_cmd.command(name="delete")
@click.argument("project")
@click.option("--force", "-f", is_flag=True, help="跳过确认直接删除")
def project_delete(project: str, force: bool) -> None:
    """删除项目"""
    from .config import HaGoKuConfig
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)

    if not pm.exists(project):
        click.echo(f"❌ 项目不存在: {project}", err=True)
        raise SystemExit(1)

    if not force:
        click.echo(f"⚠️  确定删除项目 '{project}'？此操作不可恢复。")
        try:
            confirm = input("   输入项目名确认: ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\n已取消。")
            return
        if confirm != project:
            click.echo("已取消。")
            return

    pm.delete(project)
    click.echo(f"✅ 项目已删除: {project}")


@project_cmd.command(name="run")
@click.argument("project")
@click.option("--data", "-d", default=None, help="指定输入文件（留空则用最新添加的文件）")
@click.option("--query", "-q", "query", default="", help="分析问题")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["html", "md", "json"]),
              help="输出格式")
def project_run(
    project: str,
    data: str | None,
    query: str,
    formats: tuple[str, ...],
) -> None:
    """在项目上下文中运行分析（自动使用项目的 input/ 数据）"""
    from .config import HaGoKuConfig
    from .manager.orchestrator import Orchestrator
    from hagoku.repository.project import ProjectRepository

    config = HaGoKuConfig.load()
    pm = ProjectRepository(config.output.project_dir)

    # 获取数据文件
    if data:
        data_path = pm.get_data_path(project, data)
        if data_path is None:
            click.echo(f"❌ 项目中找不到文件: {data}", err=True)
            raise SystemExit(1)
    else:
        data_path = pm.get_latest_data(project)
        if data_path is None:
            click.echo(f"❌ 项目 '{project}' 暂无输入文件", err=True)
            click.echo(f"   添加数据: hagoku project add {project} <文件路径>")
            raise SystemExit(1)
        click.echo(f"📄 使用: {data_path.name}")

    # 创建编排器
    orch = Orchestrator(config)

    format_list = list(formats) if formats else None
    try:
        result = orch.run(
            data_path=str(data_path),
            query=query,
            project_name=project,
            formats=format_list,
        )
    except FileNotFoundError:
        click.echo("❌ 数据文件未找到", err=True)
        raise SystemExit(1)
    except RuntimeError as e:
        click.echo(f"❌ 分析失败: {e}", err=True)
        raise SystemExit(1)

    if result["status"] == "completed":
        click.echo(f"\n✅ 分析完成！报告: {result['output_path']}")
    elif result["status"] == "guardrails_blocked":
        click.echo("\n⚠️ 统计护栏（强制级）未通过，已跳过正式报告。", err=False)
        click.echo(f"   说明文件: {result.get('output_path', '')}")
    else:
        click.echo("\n❌ 分析未能完成", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("project_name", required=False)
@click.option("--category", "-c", default=None, help="按类别过滤 (column_semantic/cleaning_pref/analysis_pattern/target_variable/user_note)")
@click.option("--set", "set_item", nargs=3, type=(str, str, str), default=None,
              help="设置记忆: --set <category> <key> <value>")
@click.option("--delete", "delete_item", nargs=2, type=(str, str), default=None,
              help="删除记忆: --delete <category> <key>")
@click.option("--global", "is_global", is_flag=True, help="操作全局记忆（非项目级）")
@click.option("--export", "export_path", default=None, type=click.Path(),
              help="导出 progress.yaml 到指定路径")
@click.option("--import", "import_path", default=None, type=click.Path(exists=True),
              help="从 progress.yaml 导入记忆")
def memory(project_name: str | None, category: str | None, set_item: tuple | None,
           delete_item: tuple | None, is_global: bool,
           export_path: str | None, import_path: str | None) -> None:
    """查看/管理项目记忆"""
    from .storage.database import HaGoKuDB
    from .storage.memory import MemoryManager

    config = HaGoKuConfig.load()
    db = HaGoKuDB.get_instance(config.work_dir / "hagoku.db")

    pid = None if is_global else project_name

    # 创建 MemoryManager（不绑定 progress_path，CLI 级别操作不自动读写 YAML）
    mm = MemoryManager(db)

    # 导入 progress.yaml
    if import_path:
        target_pid = pid or project_name or "_imported"
        n = mm.import_progress_yaml(target_pid, Path(import_path))
        click.echo(f"📄 从 {import_path} 导入了 {n} 条记忆到项目 '{target_pid}'")
        return

    # 导出 progress.yaml
    if export_path:
        export_pid: str | None = pid or project_name
        if not export_pid:
            click.echo("❌ 导出需要指定项目名或 --global")
            return
        out_path = mm.export_progress_yaml(export_pid, Path(export_path))
        click.echo(f"📄 已导出 progress.yaml 到 {out_path}")
        return

    # 设置记忆
    if set_item:
        cat, key, value = set_item
        mm.save(pid, cat, key, value, source="user")
        scope = "全局" if pid is None else f"项目 '{pid}'"
        click.echo(f"✅ 已保存{scope}记忆: {cat}/{key} = {value}")
        return

    # 删除记忆
    if delete_item:
        cat, key = delete_item
        if mm.delete(pid, cat, key):
            click.echo(f"🗑️ 已删除记忆: {cat}/{key}")
        else:
            click.echo(f"未找到记忆: {cat}/{key}")
        return

    # 查看记忆
    if pid is None and not is_global:
        # 显示所有项目的记忆概览
        click.echo("🧠 记忆概览:")
        projs = db.list_projects()
        if not projs:
            click.echo("   暂无项目记忆。运行 `hagoku run` 后自动积累。")
            return
        for p in projs:
            mems = mm.load(p["id"])
            click.echo(f"   📁 {p['id']}: {len(mems)} 条记忆")
        # 全局记忆
        global_mems = mm.load(None)
        if global_mems:
            click.echo(f"   🌐 全局: {len(global_mems)} 条记忆")
        return

    # 显示指定项目的记忆
    mems = mm.load(pid, category=category)
    scope = "全局" if pid is None else f"项目 '{pid}'"
    if not mems:
        click.echo(f"{scope}暂无记忆。")
        return

    click.echo(f"🧠 {scope}记忆 ({len(mems)} 条):")
    click.echo()

    # 按类别分组
    by_category: dict[str, list] = {}
    for m in mems:
        cat = m["category"]
        by_category.setdefault(cat, []).append(m)

    category_icons = {
        "column_semantic": "🏷️",
        "cleaning_pref": "🧹",
        "analysis_pattern": "📊",
        "target_variable": "🎯",
        "user_note": "📝",
    }

    for cat, items in by_category.items():
        icon = category_icons.get(cat, "📌")
        click.echo(f"  {icon} {cat}:")
        for item in items:
            source_tag = {"user": "👤", "auto": "🤖", "learned": "📖"}.get(item.get("source", ""), "•")
            val = item.get("value", "")
            val_str = str(val)[:80] if isinstance(val, (dict, list)) else str(val)[:80]
            click.echo(f"    {source_tag} {item['key']}: {val_str}")
            if item.get("updated_at"):
                click.echo(f"       更新: {item['updated_at'][:19]}")
        click.echo()


MAX_REFINEMENT_TURNS = 5


def _run_refinement_loop(
    data_path: str,
    project_name: str | None,
    result: dict,
    orch: Any,
    verbosity: str,
) -> None:
    """交互式 refinement REPL loop

    限制：最多 5 轮结构性调整，防止演变成自由 LLM 对话
    """
    from .manager.refinement import parse_refinement

    click.echo()
    click.echo("─" * 50)
    click.echo("💬 交互模式：我会根据当前报告调整格式和范围")
    click.echo("   支持：缩小范围 / 换指标 / 简化/详细 / 解释结论")
    click.echo("   输入「退出」结束并保存报告")
    click.echo()

    refinement_context: dict[str, Any] = {
        "recent_results": [],
        "current_template": None,
        "verbosity": "standard",
    }
    turn = 0

    while turn < MAX_REFINEMENT_TURNS:
        turn += 1
        remaining = MAX_REFINEMENT_TURNS - turn

        try:
            prompt = f"\n📝 [第{turn}轮，剩{remaining}次调整机会] 你的想法: "
            feedback = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\n\n再见！报告已保存。")
            break

        if not feedback:
            continue

        # 解析用户反馈
        intent = parse_refinement(feedback, refinement_context)

        # 退出处理
        if intent.refine_type == "exit":
            click.echo("\n✅ 好的！报告已保存，随时可以继续分析。")
            break

        # 被拦截的反馈（给出引导，不算一轮）
        if intent.refine_type == "blocked":
            click.echo(f"\n{intent.guidance}")
            turn -= 1  # 不消耗轮次
            continue

        # 无法理解的反馈
        if intent.refine_type == "unknown":
            click.echo(f"\n{intent.guidance}")
            turn -= 1  # 不消耗轮次
            continue

        # 描述将要做的调整
        desc = _describe_refinement(intent)
        if desc:
            click.echo(f"\n🔄 {desc}")

        # 执行调整后的重新分析
        try:
            # 根据 refinement 类型构建新的分析参数
            new_query = _build_refinement_query(result, intent)

            if intent.refine_type == "simplify":
                refinement_context["verbosity"] = "brief"
            elif intent.refine_type == "more_detail":
                refinement_context["verbosity"] = "detailed"

            # 重新运行分析（用新 query 或调整参数）
            new_result = orch.run(
                data_path=data_path,
                query=new_query or result.get("query", ""),
                project_name=project_name,
                resume=True,
            )

            if new_result["status"] == "completed":
                click.echo(f"\n✅ 调整完成！报告: {new_result['output_path']}")
                # 更新结果用于下次 refinement
                result.update(new_result)
            elif new_result["status"] == "guardrails_blocked":
                click.echo("\n⚠️ 调整完成，但护栏阻止正式报告: ", err=False)
                click.echo(f"   {new_result.get('output_path', '')}", err=False)
                result.update(new_result)
            else:
                click.echo("\n⚠️ 调整失败，报告保持不变")

        except Exception:
            click.echo("\n⚠️ 调整出错，请重试或输入「退出」保存报告")

        # 最后一轮，给出提示
        if turn == MAX_REFINEMENT_TURNS:
            click.echo()
            click.echo("─" * 50)
            click.echo("🎉 本轮交互已达上限！")
            click.echo("   报告已保存，你可以：")
            click.echo("   • 用新问题重新运行 hagoku run（基于已有记忆）")
            click.echo("   • 修改数据后重新分析")
            click.echo("   • 输入「退出」直接结束")
            try:
                more = input("\n   还想继续调整吗？(y/n): ").strip().lower()
                if more == "y":
                    turn -= 1  # 再给一次机会
            except (EOFError, KeyboardInterrupt):
                break


def _describe_refinement(intent: Any) -> str:
    """将 refinement 意图翻译成用户能理解的话"""
    descriptions = {
        "filter": f"只看「{intent.filter_value or intent.filter_column}」的数据",
        "exclude": f"排除「{intent.filter_value or intent.filter_column}」的数据",
        "switch_target": f"换成「{intent.new_target}」作为分析指标",
        "simplify": "简化报告，只保留关键发现",
        "more_detail": "生成更详细的报告",
        "explain": "解释分析结论背后的原因",
        "blocked": "这个方向需要新的分析（退出后可重新 run）",
    }
    return descriptions.get(intent.refine_type, "")


def _build_refinement_query(original_result: dict, intent: Any) -> str:
    """根据 refinement 意图构建新的分析 query"""
    orig_query: str = original_result.get("query", "") or ""
    if intent.refine_type == "filter" and intent.filter_column:
        val = intent.filter_value or f"[指定{intent.filter_column}]"
        return f"{orig_query} {intent.filter_column}为{val}"
    elif intent.refine_type == "exclude" and intent.filter_column:
        val = intent.filter_value or f"[指定{intent.filter_column}]"
        return f"{orig_query} 排除{val}"
    elif intent.refine_type == "switch_target" and intent.new_target:
        return f"{orig_query} 指标改为{intent.new_target}"
    elif intent.refine_type == "simplify":
        return f"{orig_query} 报告简化为关键发现"
    elif intent.refine_type == "more_detail":
        return f"{orig_query} 报告详细展开"
    else:
        return orig_query


def main() -> None:
    """入口点"""
    # 无参数时显示欢迎画面（--help / --version 走正常流程）
    if len(sys.argv) == 1:
        click.echo(WELCOME_SCREEN)
        return
    cli()


if __name__ == "__main__":
    main()
