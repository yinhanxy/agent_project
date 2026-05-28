<template>
  <div class="app">
    <router-view v-slot="{ Component }">
      <!-- keep-alive 容器始终存在：切到 keepAlive:false 的页面（如账号管理）时
           不会销毁缓存，AIChat 等被缓存的页面切回时仍能保留状态 -->
      <keep-alive>
        <component :is="Component" v-if="$route.meta.keepAlive" />
      </keep-alive>
      <component :is="Component" v-if="!$route.meta.keepAlive" />
    </router-view>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import axios from 'axios'
import { useUserStore } from './store/user'

const userStore = useUserStore()

// 应用启动时拉取管理员状态，解决刷新后状态丢失
onMounted(async () => {
  const token = localStorage.getItem('jwt_token')
  if (!token) return
  try {
    const res = await axios.get('/api/kb/list', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (typeof res.data?.data?.is_admin === 'boolean') {
      userStore.isAdmin = res.data.data.is_admin
    }
  } catch {}
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-size: 16px;
  background-color: #f7f8fa;
  color: #333;
  height: 100%;
  width: 100%;
}

.app {
  max-width: 750px;
  margin: 0 auto;
  height: 100%;
  background-color: #f5f7f8;
}
</style>
