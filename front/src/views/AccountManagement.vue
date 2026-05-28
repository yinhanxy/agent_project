<template>
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
          <van-button size="small" plain icon="replay" :loading="loading" @click="loadUsers" />
        </div>

        <van-loading v-if="loading" size="24px" vertical style="padding:32px 0">加载中</van-loading>
        <van-empty v-else-if="users.length === 0" description="暂无账号" image-size="80" />

        <van-cell-group v-else inset>
          <van-cell
            v-for="u in users"
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
</template>

<script setup>
import { ref, computed, onActivated } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import axios from 'axios'
import TabBar from '../components/TabBar.vue'

const users = ref([])
const loading = ref(false)
const toggling = ref(null)

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
</style>
