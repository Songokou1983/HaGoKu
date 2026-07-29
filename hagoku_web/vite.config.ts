/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_PROXY = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
  },
  "/ws": {
    target: "ws://127.0.0.1:8000",
    ws: true,
    timeout: 0,  // 禁用代理超时，LLM 调用可能耗时 2+ 分钟
  },
} as const;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    hmr: false,  // 禁用热更新：分析中 HMR 触发 WS 断联会导致状态丢失
    proxy: { ...API_PROXY },
    watch: {
      ignored: ["**/.venv/**", "**/__pycache__/**", "**/.git/**", "**/.mypy_cache/**", "**/.pytest_cache/**", "**/dist/**", "**/*.db"],
    },
  },
  // `vite preview` 不走 server.proxy；不配则 /api 打到预览进程本身，列表请求易挂死
  preview: {
    proxy: { ...API_PROXY },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
})
