import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 端口与代理目标支持环境变量覆盖，便于多项目并存时避开端口冲突。
// 默认值与原配置一致：前端 3000、FastAPI 8000、Django 8001。
// 例（本项目后端改跑 8010 时）：
//   set API_TARGET=http://127.0.0.1:8010 && npm run dev
const FRONT_PORT = Number(process.env.FRONT_PORT) || 3000
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8000'   // FastAPI
const USER_TARGET = process.env.USER_TARGET || 'http://127.0.0.1:8001' // Django

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: FRONT_PORT,
    host: true, // 允许局域网访问
    proxy: {
      // 所有 /api 接口代理到 FastAPI
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true
      },
      // 用户相关接口代理到 Django
      '/user': {
        target: USER_TARGET,
        changeOrigin: true
      },
      '/file': {
        target: USER_TARGET,
        changeOrigin: true
      }
    }
  }
})
