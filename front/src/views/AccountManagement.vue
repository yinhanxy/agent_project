<template>
  <workbench-layout page-class="admin-workbench" sidebar-label="账号筛选" context-label="账号上下文" single-content>
    <template #rail>
      <desktop-rail />
    </template>

    <template #sidebar>
      <div class="admin-side-header">
        <span class="side-eyebrow">权限管理</span>
        <h2>账号</h2>
      </div>

      <label class="admin-search">
        <van-icon name="search" size="16" />
        <input v-model="userSearch" type="search" placeholder="搜索账号或邮箱" />
      </label>

      <div class="admin-filter-list">
        <button type="button" :class="{ active: roleFilter === 'all' }" @click="roleFilter = 'all'">
          全部账号 <strong>{{ users.length }}</strong>
        </button>
        <button type="button" :class="{ active: roleFilter === 'admin' }" @click="roleFilter = 'admin'">
          管理员 <strong>{{ adminCount }}</strong>
        </button>
        <button type="button" :class="{ active: roleFilter === 'normal' }" @click="roleFilter = 'normal'">
          普通用户 <strong>{{ normalCount }}</strong>
        </button>
      </div>

      <button class="admin-side-action" type="button" @click="goToRegister">
        <van-icon name="plus" size="14" />
        新增账号
      </button>
    </template>

    <div class="account-container">
    <van-nav-bar title="账号管理" fixed />

    <div class="account-content">
      <!-- 统计卡片 -->
      <div class="stat-card">
        <div class="stat-item">
          <span class="stat-num">{{ users.length }}</span>
          <span class="stat-label">总账号数</span>
        </div>
        <div class="stat-divider" />
        <div class="stat-item">
          <span class="stat-num">{{ adminCount }}</span>
          <span class="stat-label">管理员</span>
        </div>
        <div class="stat-divider" />
        <div class="stat-item">
          <span class="stat-num">{{ users.length - adminCount }}</span>
          <span class="stat-label">普通用户</span>
        </div>
      </div>

      <!-- 用户列表 -->
      <div class="list-section">
        <div class="section-header">
          <span class="section-title">账号列表</span>
          <div class="section-actions">
            <van-button size="small" type="primary" icon="plus" @click="goToRegister">
              新增账号
            </van-button>
            <van-button size="small" plain icon="replay" :loading="loading" @click="loadUsers" />
          </div>
        </div>

        <van-loading v-if="loading" size="24px" vertical style="padding:32px 0">加载中</van-loading>
        <van-empty v-else-if="filteredUsers.length === 0" description="暂无账号" image-size="80" />

        <van-cell-group v-else inset>
          <van-cell
            v-for="u in filteredUsers"
            :key="u.uuid"
            :title="u.username"
            :label="u.email"
          >
            <template #icon>
              <van-icon
                name="manager"
                :color="u.is_admin ? '#1989fa' : '#ccc'"
                size="22"
                style="margin-right:10px;flex-shrink:0"
              />
            </template>
            <template #right-icon>
              <div style="display:flex;align-items:center;gap:8px">
                <van-tag v-if="u.is_admin" type="primary">管理员</van-tag>
                <van-tag v-else type="default">普通用户</van-tag>
                <van-switch
                  :model-value="u.is_admin"
                  size="20px"
                  :disabled="toggling === u.uuid || u.uuid === selfUuid"
                  :loading="toggling === u.uuid"
                  @update:model-value="toggleAdmin(u)"
                />
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </div>

      <!-- 说明 -->
      <div style="padding:0 20px;margin-top:8px">
        <p style="font-size:12px;color:#999;line-height:1.6">
          · 管理员可创建部门/管理员专属知识库，可访问所有知识库<br>
          · 不能修改自己的权限<br>
          · 权限变更后，对方需退出重新登录才能生效
        </p>
      </div>
    </div>

      <tab-bar />
    </div>

    <template #context>
      <section class="admin-context-card">
        <div class="admin-context-title">
          <h3>账号统计</h3>
          <span>{{ users.length }}</span>
        </div>
        <div class="admin-context-list">
          <div><span>管理员</span><strong>{{ adminCount }}</strong></div>
          <div><span>普通用户</span><strong>{{ normalCount }}</strong></div>
          <div><span>当前筛选</span><strong>{{ filteredUsers.length }}</strong></div>
        </div>
      </section>

      <section class="admin-context-card">
        <div class="admin-context-title">
          <h3>权限说明</h3>
        </div>
        <p class="admin-context-note">
          管理员可创建部门/管理员专属知识库，可访问所有知识库。不能修改自己的权限，权限变更后对方需重新登录。
        </p>
      </section>
    </template>
  </workbench-layout>
</template>

<script setup>
import { ref, computed, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showConfirmDialog } from 'vant'
import axios from 'axios'
import DesktopRail from '../components/DesktopRail.vue'
import TabBar from '../components/TabBar.vue'
import WorkbenchLayout from '../components/WorkbenchLayout.vue'

const router = useRouter()
const users = ref([])
const loading = ref(false)
const toggling = ref(null)
const userSearch = ref('')
const roleFilter = ref('all')

const getToken = () => localStorage.getItem('jwt_token') || ''
const authHeader = () => ({ Authorization: `Bearer ${getToken()}` })

// 当前登录用户 uuid（从 JWT payload 解析）
const selfUuid = computed(() => {
  try {
    const token = getToken()
    if (!token) return ''
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.user_id || ''
  } catch {
    return ''
  }
})

const adminCount = computed(() => users.value.filter(u => u.is_admin).length)
const normalCount = computed(() => users.value.length - adminCount.value)
const filteredUsers = computed(() => {
  const keyword = userSearch.value.trim().toLowerCase()
  return users.value.filter(user => {
    const roleMatched = roleFilter.value === 'all'
      || (roleFilter.value === 'admin' && user.is_admin)
      || (roleFilter.value === 'normal' && !user.is_admin)
    const textMatched = !keyword
      || [user.username, user.email, user.uuid].some(value => String(value || '').toLowerCase().includes(keyword))
    return roleMatched && textMatched
  })
})

const goToRegister = () => {
  router.push('/register')
}

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/admin/users', { headers: authHeader() })
    users.value = res.data?.users || []
  } catch (e) {
    showToast('加载失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    loading.value = false
  }
}

const toggleAdmin = async (u) => {
  const action = u.is_admin ? '取消' : '授予'
  try {
    await showConfirmDialog({
      title: `${action}管理员权限`,
      message: `确认${action} ${u.username} 的管理员权限？`,
    })
  } catch {
    return
  }

  toggling.value = u.uuid
  try {
    const res = await axios.patch(
      `/api/admin/users/${u.uuid}/set-admin`,
      {},
      { headers: authHeader() }
    )
    u.is_admin = res.data?.is_admin ?? !u.is_admin
    showToast(`已${action}管理员权限`)
  } catch (e) {
    showToast('操作失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    toggling.value = null
  }
}

// 页面已开启 keep-alive：用 onActivated 保证每次进入都刷新用户列表（首次挂载也会触发）
onActivated(loadUsers)
</script>

<style scoped>
.account-container { min-height: 100vh; background: #f7f8fa; }
.account-content { padding-top: 46px; padding-bottom: 60px; }

.admin-side-header {
  margin-bottom: 14px;
}

.side-eyebrow {
  color: var(--workbench-teal, #178c83);
  font-size: 12px;
  font-weight: 800;
}

.admin-side-header h2 {
  margin: 2px 0 0;
  color: var(--workbench-ink, #16202a);
  font-size: 19px;
  line-height: 1.2;
}

.admin-search,
.admin-side-action {
  display: flex;
  align-items: center;
}

.admin-search {
  gap: 8px;
  height: 40px;
  margin-bottom: 12px;
  padding: 0 12px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 10px;
  background: #ffffff;
  color: var(--workbench-muted, #6b7684);
}

.admin-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--workbench-ink, #16202a);
  font-size: 13px;
}

.admin-filter-list {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.admin-filter-list button,
.admin-side-action {
  width: 100%;
  border: 0;
  cursor: pointer;
}

.admin-filter-list button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--workbench-muted, #6b7684);
  font-size: 13px;
  font-weight: 800;
}

.admin-filter-list button.active,
.admin-filter-list button:hover {
  border-color: #c8ddf4;
  background: #ffffff;
  color: var(--workbench-primary, #1d6fe8);
  box-shadow: 0 10px 28px rgba(31, 122, 224, 0.08);
}

.admin-side-action {
  justify-content: center;
  gap: 6px;
  height: 38px;
  border-radius: 10px;
  background: var(--workbench-primary, #1d6fe8);
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
}

.admin-context-card {
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 14px;
  background: #ffffff;
}

.admin-context-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.admin-context-title h3 {
  margin: 0;
  color: var(--workbench-ink, #16202a);
  font-size: 14px;
}

.admin-context-title span {
  color: var(--workbench-primary, #1d6fe8);
  font-size: 12px;
  font-weight: 800;
}

.admin-context-list {
  display: grid;
  gap: 8px;
}

.admin-context-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--workbench-muted, #6b7684);
  font-size: 12px;
}

.admin-context-list strong {
  color: var(--workbench-ink, #16202a);
}

.admin-context-note {
  margin: 0;
  color: var(--workbench-muted, #6b7684);
  font-size: 13px;
  line-height: 1.6;
}

@media screen and (min-width: 901px) {
  .account-container {
    min-height: 100%;
    background: transparent;
    overflow-y: auto;
  }

  .account-content {
    padding-top: 0;
    padding-bottom: 20px;
  }

  .account-container :deep(.van-nav-bar),
  .account-container :deep(.app-tabbar) {
    display: none;
  }
}

.stat-card {
  display: flex;
  align-items: center;
  background: #fff;
  margin: 12px 16px;
  border-radius: 12px;
  padding: 16px 0;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stat-num { font-size: 24px; font-weight: 700; color: #1989fa; }
.stat-label { font-size: 12px; color: #969799; }
.stat-divider { width: 1px; height: 32px; background: #eee; }

.list-section { padding: 0 16px; margin-top: 4px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 4px;
}
.section-title { font-size: 14px; font-weight: 500; color: #323233; }
.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
