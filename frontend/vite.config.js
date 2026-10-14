import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 转发到本地 FastAPI 后端
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
