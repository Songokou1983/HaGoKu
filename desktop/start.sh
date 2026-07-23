#!/bin/bash
# HaGoKu Desktop — 一键启动
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$DIR/.."

# 清理已有进程（等待端口释放）
# 先杀掉所有旧 Electron 残留（桌面端关闭后 GPU/utility 进程可能存活）
pkill -f 'electron.*hagoku' 2>/dev/null || true
sleep 1

for port in 8000 5173; do
  fuser -k ${port}/tcp 2>/dev/null || true
  for _ in $(seq 1 10); do
    fuser ${port}/tcp 2>/dev/null || break
    sleep 0.5
  done
done

# 确保退出时清理后台进程
cleanup() { kill $API_PID $VITE_PID 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

# 1. API
echo "🔧 HaGoKu API..."
cd "$PROJECT"
.venv/bin/python3 -m uvicorn hagoku.api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# 等待 API 就绪
for _ in $(seq 1 10); do
  curl -s -o /dev/null http://localhost:8000/api/health && break
  sleep 0.5
done
echo "   ✅ API ready"

# 2. 前端
echo "🎨 前端..."
cd "$PROJECT/hagoku_web"
npx vite --host 0.0.0.0 --port 5173 --clearScreen false &
VITE_PID=$!

# 等待前端就绪
for _ in $(seq 1 15); do
  curl -s -o /dev/null http://localhost:5173 && break
  sleep 0.5
done
echo "   ✅ 前端 ready"

# 3. 桌面
echo "🖥️ HaGoKu Studio..."
cd "$DIR"
npx electron . --no-sandbox