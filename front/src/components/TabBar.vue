<template>
  <van-tabbar v-model="active" route>
    <van-tabbar-item to="/aichat" icon="chat-o">{{ $t('nav.aiChat') }}</van-tabbar-item>
    <van-tabbar-item to="/sessions" icon="comment-circle-o">{{ $t('nav.sessions') }}</van-tabbar-item>
    <van-tabbar-item to="/knowledge" icon="orders-o">知识库</van-tabbar-item>
    <van-tabbar-item v-if="userStore.isAdmin" to="/admin/accounts" icon="manager-o">账号管理</van-tabbar-item>
    <van-tabbar-item to="/my" icon="user-o">{{ $t('nav.my') }}</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '../store/user'

const route = useRoute()
const userStore = useUserStore()
const active = ref(0)

const setActiveTab = () => {
  const path = route.path
  if (path.includes('/aichat')) {
    active.value = 0
  } else if (path.includes('/sessions')) {
    active.value = 1
  } else if (path.includes('/knowledge')) {
    active.value = 2
  } else if (path.includes('/admin/accounts')) {
    active.value = 3
  } else if (path.includes('/my')) {
    active.value = userStore.isAdmin ? 4 : 3
  }
}

setActiveTab()

watch(() => route.path, setActiveTab)
</script>
