import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 开发时把 /api 转发到本地 FastAPI
      '/api': {
        target: 'http://127.0.0.1:8210',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 单容器部署：构建产物直接落到 backend/static
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})
