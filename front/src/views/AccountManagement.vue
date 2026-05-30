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
            <template #value>
              <div class="user-meta">
                <div class="user-tags">
                  <van-tag v-if="u.is_admin" type="primary">总管理员</van-tag>
                  <van-tag v-else-if="u.is_dept_admin" type="success">部门管理员</van-tag>
                  <van-tag v-else type="default">普通用户</van-tag>
                  <van-tag plain type="warning">{{ u.dept_name || '未分配部门' }}</van-tag>
                </div>
                <div class="user-actions">
                  <span class="user-role-label">总管理员</span>
                  <van-switch
                    :model-value="u.is_admin"
                    size="18px"
                    :disabled="toggling === u.uuid || u.uuid === selfUuid"
                    :loading="toggling === u.uuid"
                    @update:model-value="toggleAdmin(u)"
                  />
                  <van-button
                    size="mini"
                    plain
                    type="primary"
                    :disabled="u.is_admin"
                    @click="openAssignDept(u)"
                  >分配部门</van-button>
                  <van-button
                    size="mini"
                    plain
                    :type="u.is_dept_admin ? 'danger' : 'success'"
                    :disabled="!u.dept_id || u.is_admin || deptAdminToggling === u.uuid"
                    :loading="deptAdminToggling === u.uuid"
                    @click="toggleDeptAdmin(u)"
                  >{{ u.is_dept_admin ? '取消部管' : '任命部管' }}</van-button>
                </div>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </div>

      <!-- 部门管理 -->
      <div class="list-section" v-if="isSuperAdmin">
        <div class="section-header">
          <span class="section-title">部门管理</span>
          <div class="section-actions">
            <van-button size="small" type="primary" icon="plus" @click="openCreateDept">
              新建部门
            </van-button>
            <van-button size="small" plain icon="replay" :loading="loadingDepts" @click="loadDepartments" />
          </div>
        </div>

        <van-loading v-if="loadingDepts" size="24px" vertical style="padding:24px 0">加载中</van-loading>
        <van-empty v-else-if="departments.length === 0" description="暂无部门" image-size="80" />
        <div v-else class="department-list">
          <section
            v-for="d in departmentSummaries"
            :key="d.dept_id"
            class="department-card"
          >
            <div class="department-card-head">
              <div class="department-title">
                <h3>{{ d.name }}</h3>
                <span>{{ d.memberCount }} 人</span>
              </div>
              <div class="department-actions">
                <van-button size="mini" plain @click="renameDept(d)">改名</van-button>
                <van-button size="mini" plain type="danger" @click="deleteDept(d)">删除</van-button>
              </div>
            </div>

            <div class="department-stats">
              <div><span>部门管理员</span><strong>{{ d.deptAdminCount }}</strong></div>
              <div><span>普通成员</span><strong>{{ d.normalMemberCount }}</strong></div>
            </div>

            <div v-if="d.members.length" class="department-members">
              <div v-for="member in d.members" :key="member.uuid" class="department-member">
                <div class="member-info">
                  <strong>{{ member.username }}</strong>
                  <span>{{ member.email || '未填写邮箱' }}</span>
                </div>
                <div class="member-tags">
                  <van-tag v-if="member.is_admin" type="primary">总管理员</van-tag>
                  <van-tag v-else-if="member.is_dept_admin" type="success">部门管理员</van-tag>
                  <van-tag v-else type="default">普通成员</van-tag>
                </div>
              </div>
            </div>
            <div v-else class="department-empty">暂无成员</div>
          </section>
        </div>
      </div>

      <!-- 说明 -->
      <div style="padding:0 20px;margin-top:8px">
        <p style="font-size:12px;color:#999;line-height:1.6">
          · 总管理员可创建公开/部门/管理员专属知识库，可访问所有知识库<br>
          · 部门管理员可创建并管理本部门知识库（需先归属某部门）<br>
          · 任命部门管理员前，该账号需先被分配到某个部门<br>
          · 不能修改自己的权限<br>
          · 权限变更后，对方需退出重新登录才能生效
        </p>
      </div>
    </div>

      <tab-bar />
    </div>

    <!-- 分配部门 -->
    <van-action-sheet
      v-model:show="showAssignDept"
      :actions="assignDeptActions"
      cancel-text="取消"
      :description="assignTarget ? `为「${assignTarget.username}」选择部门` : ''"
      @select="onAssignDept"
    />

    <van-dialog
      v-model:show="showCreateDeptDialog"
      title="新建部门"
      show-cancel-button
      :before-close="beforeCreateDeptClose"
    >
      <van-field
        v-model="newDeptName"
        label="部门名称"
        placeholder="请输入部门名称"
        :disabled="creatingDept"
        maxlength="32"
        clearable
      />
    </van-dialog>

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
import { useUserStore } from '../store/user'
import { buildDepartmentSummaries } from '../utils/departmentSummary'

const router = useRouter()
const users = ref([])
const loading = ref(false)
const toggling = ref(null)
const userSearch = ref('')
const roleFilter = ref('all')

const userStore = useUserStore()
const isSuperAdmin = computed(() => userStore.isSuperAdmin)

// ── 部门数据 ──────────────────────────────────────────────────
const departments = ref([])
const loadingDepts = ref(false)

// 分配部门
const showAssignDept = ref(false)
const assignTarget = ref(null)   // 正在分配部门的用户
const assigningDept = ref(false)

// 任命部门管理员
const deptAdminToggling = ref(null)

// 部门 CRUD
const newDeptName = ref('')
const creatingDept = ref(false)
const showCreateDeptDialog = ref(false)

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
const departmentSummaries = computed(() => buildDepartmentSummaries(departments.value, users.value))

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

const loadDepartments = async () => {
  if (!isSuperAdmin.value) return
  loadingDepts.value = true
  try {
    const res = await axios.get('/api/admin/departments', { headers: authHeader() })
    departments.value = res.data?.departments || []
  } catch (e) {
    showToast('加载部门失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    loadingDepts.value = false
  }
}

// ── 分配部门 ────────────────────────────────────────────────
const openAssignDept = (u) => {
  assignTarget.value = u
  showAssignDept.value = true
}

// 部门分配 action-sheet 选项：各部门 + 「移出部门」
const assignDeptActions = computed(() => {
  const actions = departments.value.map(d => ({ name: d.name, dept_id: d.dept_id }))
  actions.push({ name: '移出部门', dept_id: null, color: '#ee0a24' })
  return actions
})

const onAssignDept = async (action) => {
  const u = assignTarget.value
  if (!u) return
  assigningDept.value = true
  try {
    await axios.patch(
      `/api/admin/users/${u.uuid}/set-dept`,
      { dept_id: action.dept_id },
      { headers: authHeader() }
    )
    showToast(action.dept_id ? `已分配到「${action.name}」` : '已移出部门')
    await loadUsers()   // 重新拉取，刷新 dept_name / is_dept_admin
  } catch (e) {
    showToast('操作失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    assigningDept.value = false
    assignTarget.value = null
  }
}

// ── 任命/取消部门管理员 ──────────────────────────────────────
const toggleDeptAdmin = async (u) => {
  if (!u.dept_id) { showToast('请先为该账号分配部门'); return }
  const next = !u.is_dept_admin
  const action = next ? '任命' : '取消'
  try {
    await showConfirmDialog({
      title: `${action}部门管理员`,
      message: `确认${action} ${u.username} 为「${u.dept_name}」的部门管理员？`,
    })
  } catch {
    return
  }
  deptAdminToggling.value = u.uuid
  try {
    const res = await axios.patch(
      `/api/admin/users/${u.uuid}/set-dept-admin`,
      { is_dept_admin: next },
      { headers: authHeader() }
    )
    u.is_dept_admin = res.data?.is_dept_admin ?? next
    showToast(`已${action}部门管理员`)
  } catch (e) {
    showToast('操作失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    deptAdminToggling.value = null
  }
}

// ── 部门 CRUD ────────────────────────────────────────────────
const openCreateDept = () => {
  newDeptName.value = ''
  showCreateDeptDialog.value = true
}

const createDept = async () => {
  const name = newDeptName.value.trim()
  if (!name) { showToast('请输入部门名称'); return false }
  creatingDept.value = true
  try {
    await axios.post('/api/admin/departments', { name }, { headers: authHeader() })
    showToast('部门已创建')
    newDeptName.value = ''
    await loadDepartments()
    return true
  } catch (e) {
    showToast('创建失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    return false
  } finally {
    creatingDept.value = false
  }
}

const beforeCreateDeptClose = async (action) => {
  if (action !== 'confirm') return true
  return createDept()
}

const renameDept = (d) => {
  showConfirmDialog({
    title: '重命名部门',
    message: `将「${d.name}」重命名为：`,
    // Vant 的 confirmDialog 无输入框，用 prompt 兜底（桌面端浏览器原生输入）
  }).then(async () => {
    const name = window.prompt('请输入新的部门名称', d.name)
    if (name === null) return
    const trimmed = name.trim()
    if (!trimmed) { showToast('部门名称不能为空'); return }
    try {
      await axios.patch(`/api/admin/departments/${d.dept_id}`, { name: trimmed }, { headers: authHeader() })
      showToast('已重命名')
      await loadDepartments()
      await loadUsers()  // 成员的 dept_name 随之更新
    } catch (e) {
      showToast('重命名失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}

const deleteDept = (d) => {
  showConfirmDialog({
    title: '删除部门',
    message: `确认删除「${d.name}」？该部门成员将被移出部门（其部门管理员身份一并解除）。`,
    confirmButtonColor: '#ee0a24',
  }).then(async () => {
    try {
      await axios.delete(`/api/admin/departments/${d.dept_id}`, { headers: authHeader() })
      showToast('部门已删除')
      await loadDepartments()
      await loadUsers()
    } catch (e) {
      showToast('删除失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
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

// 页面已开启 keep-alive：用 onActivated 保证每次进入都刷新用户列表与部门（首次挂载也会触发）
onActivated(() => {
  loadUsers()
  loadDepartments()
})
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

.user-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.user-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.user-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-role-label {
  font-size: 12px;
  color: #969799;
}

.department-list {
  display: grid;
  gap: 12px;
}

.department-card {
  padding: 14px;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}

.department-card-head,
.department-actions,
.department-member,
.member-tags {
  display: flex;
  align-items: center;
}

.department-card-head {
  justify-content: space-between;
  gap: 12px;
}

.department-title {
  min-width: 0;
}

.department-title h3 {
  margin: 0;
  color: #323233;
  font-size: 15px;
  line-height: 1.3;
  word-break: break-word;
}

.department-title span {
  display: inline-block;
  margin-top: 3px;
  color: #969799;
  font-size: 12px;
}

.department-actions {
  flex-shrink: 0;
  gap: 8px;
}

.department-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.department-stats div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  background: #f7f8fa;
  color: #646566;
  font-size: 12px;
}

.department-stats strong {
  color: #323233;
}

.department-members {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.department-member {
  justify-content: space-between;
  gap: 10px;
  min-height: 48px;
  padding: 9px 10px;
  border: 1px solid #eef0f3;
  border-radius: 10px;
}

.member-info {
  min-width: 0;
}

.member-info strong,
.member-info span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-info strong {
  color: #323233;
  font-size: 13px;
  line-height: 1.4;
}

.member-info span {
  color: #969799;
  font-size: 12px;
}

.member-tags {
  flex-shrink: 0;
  justify-content: flex-end;
}

.department-empty {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: #f7f8fa;
  color: #969799;
  font-size: 12px;
  text-align: center;
}

@media screen and (max-width: 520px) {
  .department-card-head,
  .department-member {
    align-items: flex-start;
    flex-direction: column;
  }

  .department-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .department-stats {
    grid-template-columns: 1fr;
  }
}
</style>
