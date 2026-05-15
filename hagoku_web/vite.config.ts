import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_PROXY = {
  "/api": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
  "/ws": {
    target: "ws://localhost:8000",
    ws: true,
  },
} as const;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { ...API_PROXY },
  },
  // `vite preview` 不走 server.proxy；不配则 /api 打到预览进程本身，列表请求易挂死
  preview: {
    proxy: { ...API_PROXY },
  },
})
