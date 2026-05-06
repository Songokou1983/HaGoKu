#!/bin/bash
# HaGoKu 安全工作流脚本
# 用法：
#   ./git-safe-workflow.sh backup   # 开始工作前备份
#   ./git-safe-workflow.sh save     # 完成改动后保存
#   ./git-safe-workflow.sh status   # 查看当前状态

set -e

WORK_DIR="$(git rev-parse --show-toplevel)"
cd "$WORK_DIR"

case "$1" in
    backup)
        echo "📦 创建工作前备份..."
        git add -A
        git commit -m "WIP: 工作前备份 $(date +'%Y-%m-%d %H:%M:%S')"
        echo "✅ 备份完成。如果接下来的改动有问题，执行: git reset --soft HEAD~1"
        ;;
    save)
        echo "💾 保存当前改动..."
        git add -A
        echo "请输入 commit 描述（简短描述你做了什么改动）："
        read -r msg
        if [ -z "$msg" ]; then
            echo "❌ 描述不能为空"
            exit 1
        fi
        git commit -m "$msg"
        echo "✅ 保存完成"
        ;;
    status)
        echo "📊 当前状态："
        git status
        echo ""
        echo "最近5次提交："
        git log --oneline -5
        ;;
    *)
        echo "用法:"
        echo "  $0 backup   # 开始工作前备份（必须！）"
        echo "  $0 save    # 完成改动后保存"
        echo "  $0 status  # 查看当前状态"
        ;;
esac
