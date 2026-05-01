#!/usr/bin/env python3
"""
HaGoKu 示例：广告效果分析

演示三种使用方式：
1. 数据画像 (profile)
2. 完整分析 (run)
3. 快速模式 (quick)

数据: examples/ad_campaign.csv — 50 条广告投放记录
字段: campaign_id, channel, spend, impressions, clicks, conversions, revenue, date
"""

import subprocess
import sys
from pathlib import Path

EXAMPLE_DATA = Path(__file__).parent / "ad_campaign.csv"


def run_cmd(cmd: list[str]) -> None:
    """运行命令并打印"""
    print(f"\n{'='*60}")
    print(f"$ {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent.parent))
    if result.returncode != 0:
        print(f"[WARNING] 命令返回码: {result.returncode}")


def main() -> None:
    if not EXAMPLE_DATA.exists():
        print(f"示例数据不存在: {EXAMPLE_DATA}")
        sys.exit(1)

    print("=" * 60)
    print("HaGoKu 广告效果分析示例")
    print("=" * 60)

    # 1. 数据画像
    print("\n### 1. 数据画像 — 快速了解数据全貌 ###\n")
    run_cmd(["hagokyu", "profile", str(EXAMPLE_DATA)])

    # 2. 完整分析
    print("\n### 2. 完整分析 — 提问，拿报告 ###\n")
    run_cmd([
        "hagokyu", "run", str(EXAMPLE_DATA),
        "-q", "哪个广告渠道的转化率和ROI最好？",
        "-f", "html", "-f", "md",
    ])

    # 3. 快速模式
    print("\n### 3. 快速模式 — 零交互出结果 ###\n")
    run_cmd([
        "hagokyu", "quick", str(EXAMPLE_DATA),
        "-q", "分析不同渠道的花费和收入关系",
    ])

    # 4. 查看项目历史
    print("\n### 4. 查看项目历史 ###\n")
    run_cmd(["hagokyu", "projects"])

    print("\n示例运行完毕。")
    print("报告保存在 ~/.hagokyu/projects/ 目录下。")


if __name__ == "__main__":
    main()
