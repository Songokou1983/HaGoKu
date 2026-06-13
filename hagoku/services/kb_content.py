"""知识库内容解析——YAML frontmatter 解析、注册表加载。

从 api/server.py 提取，与 HTTP 路由解耦。
"""

from __future__ import annotations

from pathlib import Path


def parse_frontmatter(raw: str) -> dict:
    """解析 YAML frontmatter，返回 {title, summary, category, tags, tools, ...}。"""
    if not raw.startswith("---"):
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        pass
    # 降级：手动解析 key: value + multi-line list
    result: dict = {}
    lines = parts[1].splitlines()
    current_key: str | None = None
    current_list: list = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_key:
            item = line[2:].strip().strip('"').strip("'")
            current_list.append(item)
            continue
        if current_key and current_list:
            result[current_key] = current_list
            current_key = None
            current_list = []
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                result[key] = val
            elif val:
                result[key] = val
            else:
                current_key = key
                current_list = []
    if current_key and current_list:
        result[current_key] = current_list
    return result


def strip_frontmatter(raw: str) -> str:
    """去除 YAML frontmatter，返回正文。"""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return raw.strip()


def load_registry_entries(methods_root: Path) -> list[dict]:
    """从 methods/ 目录加载所有知识库条目（含 frontmatter 元数据）。"""
    if not methods_root.exists():
        return []
    entries: list[dict] = []
    for md in sorted(methods_root.rglob("*.md")):
        rel = str(md.relative_to(methods_root)).replace("\\", "/")
        raw = md.read_text(encoding="utf-8")
        fm = parse_frontmatter(raw)

        # 优先使用 frontmatter title，其次从 # 标题提取
        title = fm.get("title", "")
        if not title:
            first = raw.splitlines()[:1]
            title = first[0].lstrip("# ").strip() if first else rel

        entries.append({
            "filename": rel,
            "title": title,
            "summary": fm.get("summary", ""),
            "category": fm.get("category", md.parent.name),
            "tags": fm.get("tags", []),
            "tools": fm.get("tools", []),
        })
    return entries
