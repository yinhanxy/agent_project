<template>
  <aside class="desktop-rail" aria-label="主导航">
    <button class="rail-logo" type="button" title="新对话" aria-label="新对话" @click="createNewChat">AI</button>

    <button
      v-for="item in navItems"
      :key="item.to"
      class="rail-button"
      :class="{ active: item.active }"
      type="button"
      :title="item.label"
      :aria-label="item.label"
      @click="navigateTo(item)"
    >
      <van-icon :name="item.icon" size="21" />
    </button>

    <button
      class="rail-button rail-bottom"
      :class="{ active: route.path.startsWith('/my') || route.path.startsWith('/settings') || route.path.startsWith('/profile') }"
      type="button"
      title="我的"
      aria-label="我的"
      @click="navigateTo({ to: '/my', requiresAuth: true })"
    >
      <van-icon name="user-o" size="21" />
    </button>
  </aside>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUserStore } from '../store/user';
import { useSessionStore } from '../store/session';

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const sessionStore = useSessionStore();

const isLoggedIn = () => Boolean(localStorage.getItem('jwt_token') || userStore.token);

const requireLogin = (redirect = route.fullPath) => {
  if (isLoggedIn()) return true;
  router.push(`/login?redirect=${encodeURIComponent(redirect)}`);
  return false;
};

const navItems = computed(() => {
  const items = [
    { label: 'AI问答', icon: 'chat-o', to: '/aichat', active: route.path.startsWith('/aichat') },
    { label: '知识库', icon: 'orders-o', to: '/knowledge', active: route.path.startsWith('/knowledge'), requiresAuth: true }
  ];

  if (userStore.isAdmin) {
    items.push({
      label: '账号管理',
      icon: 'manager-o',
      to: '/admin/accounts',
      active: route.path.startsWith('/admin/accounts'),
      requiresAuth: true
    });
  }

  return items;
});

const navigateTo = (item) => {
  if (item.requiresAuth && !requireLogin(item.to)) return;
  router.push(item.to);
};

const createNewChat = () => {
  if (!requireLogin('/aichat')) return;
  sessionStore.requestNewChat();
  router.push('/aichat');
};
</script>

<style scoped>
.desktop-rail {
  display: flex;
  min-height: 0;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 18px 12px;
  border-right: 1px solid var(--workbench-line, #dfe7ed);
  background: rgba(255, 255, 255, 0.78);
}

.rail-logo,
.rail-button {
  display: grid;
  place-items: center;
  border: 0;
  cursor: pointer;
}

.rail-logo {
  width: 42px;
  height: 42px;
  margin-bottom: 6px;
  border-radius: 12px;
  background: #102f4c;
  color: #ffffff;
  font-size: 13px;
  font-weight: 900;
  box-shadow: 0 12px 28px rgba(16, 47, 76, 0.2);
}

.rail-button {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: transparent;
  color: #536579;
}

.rail-button.active,
.rail-button:hover {
  background: #e8f2ff;
  color: var(--workbench-primary, #1d6fe8);
}

.rail-bottom {
  margin-top: auto;
}

@media screen and (max-width: 900px) {
  .desktop-rail {
    display: none;
  }
}
</style>
