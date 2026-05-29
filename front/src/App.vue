<template>
  <div class="app" :class="{ 'app--wide': isWideRoute }">
    <router-view v-slot="{ Component }">
      <template v-if="$route.meta.keepAlive">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </template>
      <template v-else>
        <component :is="Component" />
      </template>
    </router-view>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import axios from 'axios'
import { computed } from 'vue'
import { useUserStore } from './store/user'
import { useRoute } from 'vue-router'

const userStore = useUserStore()
const route = useRoute()
const wideRoutePrefixes = ['/aichat', '/sessions', '/knowledge', '/my', '/settings', '/admin/accounts']
const isWideRoute = computed(() => wideRoutePrefixes.some(prefix => route.path.startsWith(prefix)))

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

@media screen and (min-width: 901px) {
  .app.app--wide {
    max-width: none;
    width: 100%;
  }
}
</style>
