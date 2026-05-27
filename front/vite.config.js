import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    host: true, // 允许局域网访问
    proxy: {
      // 所有/api接口代理到FastAPI (8000)
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true
      },
      // 用户相关接口代理到Django (8001)
      '/user': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/file': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      }
    }
  }
})