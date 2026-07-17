#!/bin/bash
# HaGoKu Desktop — 一键启动
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$DIR/.."

# 清理已有进程
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
sleep 1

# 1. API
echo "🔧 HaGoKu API..."
cd "$PROJECT"
.venv/bin/python3 -m uvicorn hagoku.api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3

# 2. 前端
echo "🎨 前端..."
cd "$PROJECT/hagoku_web"
npx vite --host 0.0.0.0 --clearScreen false &
VITE_PID=$!
sleep 3

# 3. 桌面
echo "🖥️ HaGoKu Studio..."
cd "$DIR"
npx electron . --no-sandbox

# 清理
kill $VITE_PID 2>/dev/null
kill $API_PID 2>/dev/null