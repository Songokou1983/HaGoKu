#!/usr/bin/env bash
# HaGoKu 开发环境重启：API (8000) + 前端 Vite (5173)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "🔄 重启 HaGoKu 开发环境..."

# 1. 停掉旧进程
echo "  → 停止旧进程..."
lsof -ti :8000 | xargs kill 2>/dev/null || true
lsof -ti :5173 | xargs kill 2>/dev/null || true
sleep 1

# 2. 启动 API
echo "  → 启动 API (8000)..."
.venv/bin/hagoku-api &
API_PID=$!
sleep 2

# 3. 启动前端
echo "  → 启动前端 (5173)..."
npx --prefix hagoku_web vite --host 0.0.0.0 &
VITE_PID=$!
sleep 2

# 4. 验证
echo ""
echo "✅ 已启动:"
echo "   API:    http://localhost:8000  (PID $API_PID)"
echo "   前端:   http://localhost:5173  (PID $VITE_PID)"
echo ""
echo "   停止:   kill $API_PID $VITE_PID"
