"""HaGoKu CLI — 命令行入口"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .config import HaGoKuConfig


@click.group()
@click.version_option(package_name="hagokyu")
def cli() -> None:
    """HaGoKu — 用数学的力量，挖出数据背后真正的信息"""
    pass


@cli.command()
@click.argument("data_path", type=click.Path(exists=True))
@click.option("--query", "-q", default="", help="分析问题")
@click.option("--project", "-p", default=None, help="项目名")
@click.option("--mode", "-m", default=None,
              type=click.Choice(["quick", "standard", "expert"]),
              help="用户模式 (quick/standard/expert)")
@click.option("--manager-mode", default=None,
              type=click.Choice(["local_weak", "local_strong", "cloud", "pure_rule"]),
              help="Manager 模式")
@click.option("--output-dir", "-o", default=None, help="输出目录")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["html", "md", "json"]),
              help="输出格式（可多次指定）")
@click.option("--verbosity", "-v", default="normal",
              type=click.Choice(["quiet", "normal", "verbose"]),
              help="终端输出详细度")
def run(
    data_path: str,
    query: str,
    project: str | None,
    mode: str | None,
    manager_mode: str | None,
    output_dir: str | None,
    formats: tuple[str, ...],
    verbosity: str,
) -> None:
    """运行完整分析流程"""
    from .manager.orchestrator import Orchestrator
    from .observability.display import TerminalDisplay
    from .observability.event_bus import EventBus

    # 加载配置
    config = HaGoKuConfig.load()
    if manager_mode:
        config.manager.mode = manager_mode

    # 创建编排器
    orch = Orchestrator(config)

    # 替换显示为用户指定的详细度
    orch.event_bus.unsubscribe(orch.display)
    orch.display = TerminalDisplay(verbosity=verbosity)
    orch.event_bus.subscribe(orch.display)

    # 执行分析
    format_list = list(formats) if formats else None
    result = orch.run(
        data_path=data_path,
        query=query,
        project_name=project,
        user_mode=mode,
        output_dir=output_dir,
        formats=format_list,
    )

    if result["status"] == "completed":
        if verbosity != "quiet":
            click.echo(f"\n✅ 分析完成！报告: {result['output_path']}")


@cli.command(name="quick")
@click.argument("data_path", type=click.Path(exists=True))
@click.option("--query", "-q", default="", help="分析问题")
def quick_run(data_path: str, query: str) -> None:
    """快速模式：零交互，自动分析"""
    from .manager.orchestrator import Orchestrator

    config = HaGoKuConfig.load()
    orch = Orchestrator(config)

    # 静默模式
    orch.event_bus.unsubscribe(orch.display)
    from .observability.display import TerminalDisplay
    orch.display = TerminalDisplay(verbosity="quiet")
    orch.event_bus.subscribe(orch.display)

    result = orch.run(
        data_path=data_path,
        query=query,
        user_mode="quick",
    )

    if result["status"] == "completed":
        click.echo(f"\n📄 报告: {result['output_path']}")


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
    db = HaGoKuDB.get_instance(config.work_dir / "hagokyu.db")
    projs = db.list_projects()

    if not projs:
        click.echo("暂无项目。使用 `hagokyu run` 开始第一个分析。")
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
    db = HaGoKuDB.get_instance(config.work_dir / "hagokyu.db")
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
        config_path = Path.home() / ".hagokyu" / "config.yaml"
        if config_path.exists():
            config_path.unlink()
            click.echo("✅ 配置已重置为默认值")
        else:
            click.echo("配置已是默认值")
        return

    config = HaGoKuConfig.load()
    click.echo("⚙️ HaGoKu 配置:")
    click.echo(f"   LLM: {config.llm.model} @ {config.llm.base_url}")
    click.echo(f"   Manager: {config.manager.mode} (规则={config.manager.rule_weight:.0%}, AI={config.manager.llm_weight:.0%})")
    click.echo(f"   用户模式: {config.user_mode.default_mode}")
    click.echo(f"   工作目录: {config.work_dir}")
    click.echo(f"   输出格式: {', '.join(config.output.formats)}")


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
    projects_dir = config.output.base_dir

    # 查找 run 目录
    events_path = None
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for run_dir in project_dir.iterdir():
            if run_dir.name == run_id and run_dir.is_dir():
                candidate = run_dir / "events.jsonl"
                if candidate.exists():
                    events_path = candidate
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


def main() -> None:
    """入口点"""
    cli()


if __name__ == "__main__":
    main()
