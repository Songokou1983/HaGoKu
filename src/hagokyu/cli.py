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
              type=click.Choice(["balanced", "rule", "ai"]),
              help="Manager 模式: balanced=规则+AI / rule=纯规则 / ai=AI优先")
@click.option("--output-dir", "-o", default=None, help="输出目录")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["html", "md", "json"]),
              help="输出格式（可多次指定）")
@click.option("--template", "-t", default=None,
              type=click.Choice(["default", "academic", "brief", "business_analysis", "ab_test", "executive_brief", "data_audit"]),
              help="报告模板")
@click.option("--resume", is_flag=True, help="从上次断点继续分析")
@click.option("--schema", "schema_path", default=None, type=click.Path(exists=True),
              help="外部 schema.yaml 路径")
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
    template: str | None,
    resume: bool,
    schema_path: str | None,
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
    try:
        result = orch.run(
            data_path=data_path,
            query=query,
            project_name=project,
            user_mode=mode,
            output_dir=output_dir,
            formats=format_list,
            template=template,
            resume=resume,
            schema_path=schema_path,
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
    else:
        click.echo("\n❌ 分析未能完成", err=True)
        click.echo("   请检查数据质量，或使用 -v verbose 查看详细信息", err=True)
        raise SystemExit(1)


@cli.command(name="quick")
@click.argument("data_path", type=click.Path(exists=True))
@click.option("--query", "-q", default="", help="分析问题（可选）")
def quick_run(data_path: str, query: str) -> None:
    """快速模式：零交互，自动分析

    示例：
        hagokyu quick data.csv                          # 自动探索
        hagokyu quick data.csv -q "哪个渠道效果最好"     # 指定问题
    """
    # 如果没指定问题，设置为自动探索
    if not query:
        click.echo("🚀 快速模式：自动探索数据...")
        query = "探索数据特征，寻找有意义的规律和异常"

    from .manager.orchestrator import Orchestrator

    config = HaGoKuConfig.load()
    orch = Orchestrator(config)

    # 静默模式
    orch.event_bus.unsubscribe(orch.display)
    from .observability.display import TerminalDisplay
    orch.display = TerminalDisplay(verbosity="quiet")
    orch.event_bus.subscribe(orch.display)

    try:
        result = orch.run(
            data_path=data_path,
            query=query,
            user_mode="quick",
        )
    except FileNotFoundError:
        click.echo("❌ 数据文件未找到", err=True)
        click.echo("   请确认文件路径正确，支持 CSV/Excel/JSON/Parquet 格式", err=True)
        raise SystemExit(1)
    except Exception:
        click.echo("❌ 分析过程中出现意外错误", err=True)
        click.echo("   请检查数据文件或确认 LLM 服务是否可用", err=True)
        raise SystemExit(1)

    if result["status"] == "completed":
        click.echo(f"\n📄 报告: {result['output_path']}")
    else:
        click.echo("❌ 分析未能完成，请检查数据文件", err=True)
        raise SystemExit(1)


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


@cli.command()
@click.argument("project_name", required=False)
@click.option("--category", "-c", default=None, help="按类别过滤 (column_semantic/cleaning_pref/analysis_pattern/target_variable/user_note)")
@click.option("--set", "set_item", nargs=3, type=(str, str, str), default=None,
              help="设置记忆: --set <category> <key> <value>")
@click.option("--delete", "delete_item", nargs=2, type=(str, str), default=None,
              help="删除记忆: --delete <category> <key>")
@click.option("--global", "is_global", is_flag=True, help="操作全局记忆（非项目级）")
@click.option("--export", "export_path", default=None, type=click.Path(),
              help="导出 schema.yaml 到指定路径")
@click.option("--import", "import_path", default=None, type=click.Path(exists=True),
              help="从 schema.yaml 导入记忆")
def memory(project_name: str | None, category: str | None, set_item: tuple | None,
           delete_item: tuple | None, is_global: bool,
           export_path: str | None, import_path: str | None) -> None:
    """查看/管理项目记忆"""
    from .storage.database import HaGoKuDB
    from .storage.memory import MemoryManager

    config = HaGoKuConfig.load()
    db = HaGoKuDB.get_instance(config.work_dir / "hagokyu.db")

    pid = None if is_global else project_name

    # 创建 MemoryManager（不绑定 schema_path，CLI 级别操作不自动读写 YAML）
    mm = MemoryManager(db)

    # 导入 schema.yaml
    if import_path:
        target_pid = pid or project_name or "_imported"
        n = mm.import_schema_yaml(target_pid, Path(import_path))
        click.echo(f"📄 从 {import_path} 导入了 {n} 条记忆到项目 '{target_pid}'")
        return

    # 导出 schema.yaml
    if export_path:
        target_pid = pid or project_name
        if not target_pid:
            click.echo("❌ 导出需要指定项目名或 --global")
            return
        out_path = mm.export_schema_yaml(target_pid, Path(export_path))
        click.echo(f"📄 已导出 schema.yaml 到 {out_path}")
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
            click.echo("   暂无项目记忆。运行 `hagokyu run` 后自动积累。")
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


def main() -> None:
    """入口点"""
    cli()


if __name__ == "__main__":
    main()
