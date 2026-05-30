<template>
  <workbench-layout page-class="kb-workbench" sidebar-label="知识库导航" context-label="知识库上下文" single-content>
    <template #rail>
      <desktop-rail />
    </template>

    <template #sidebar>
      <div class="kb-side-header">
        <span class="side-eyebrow">文档检索中枢</span>
        <h2>知识库</h2>
      </div>

      <div class="kb-side-tabs">
        <button type="button" :class="{ active: activeTab === 'personal' }" @click="activeTab = 'personal'">
          <van-icon name="description-o" size="15" />
          个人文档
          <strong>{{ documents.length }}</strong>
        </button>
        <button type="button" :class="{ active: activeTab === 'shared' }" @click="activeTab = 'shared'">
          <van-icon name="orders-o" size="15" />
          共享知识库
          <strong>{{ kbs.length }}</strong>
        </button>
      </div>

      <div class="kb-side-section">
        <div class="kb-side-title">快捷操作</div>
        <button class="kb-side-action" type="button" @click="triggerFileInput">
          <van-icon name="plus" size="14" />
          上传文档
        </button>
        <button class="kb-side-action" type="button" @click="showCreateKb = true">
          <van-icon name="add-o" size="14" />
          创建知识库
        </button>
      </div>

      <div class="kb-side-section">
        <div class="kb-side-title">范围</div>
        <div class="kb-scope-list">
          <span v-for="group in kbGroups" :key="group.scope">
            {{ group.label }}
            <strong>{{ group.items.length }}</strong>
          </span>
        </div>
      </div>
    </template>

    <div class="kb-container">
    <header class="kb-hero">
      <div>
        <span class="section-eyebrow">
          <van-icon name="orders-o" size="13" />
          文档检索中枢
        </span>
        <h1>知识库</h1>
      </div>
      <div class="kb-hero-stats">
        <span>{{ documents.length }} 文档</span>
        <span>{{ kbs.length }} 知识库</span>
      </div>
    </header>

    <div class="kb-content">
      <!-- 模式切换 -->
      <van-tabs v-model:active="activeTab" sticky offset-top="0" class="kb-tabs">

        <!-- ── 个人文档 ── -->
        <van-tab title="个人文档" name="personal">
          <div class="tab-body">
            <!-- 上传区域 -->
            <div class="upload-area" @click="triggerFileInput" @dragover.prevent @drop.prevent="handleDrop">
              <div class="upload-icon">
                <van-icon name="plus" size="28" />
              </div>
              <div class="upload-copy">
                <p class="upload-title">上传知识文件</p>
                <p class="upload-hint">支持 PDF、TXT、MD、DOCX、PPTX，单文件最大 20MB</p>
              </div>
              <input
                ref="fileInputRef"
                type="file"
                multiple
                accept=".pdf,.txt,.md,.docx,.pptx"
                style="display:none"
                @change="handleFileSelect"
              />
            </div>

            <!-- 待上传 -->
            <div v-if="pendingFiles.length > 0" class="list-section">
              <div class="section-header">
                <span class="section-title">待上传 <em>{{ pendingFiles.length }}</em></span>
                <van-button class="soft-button primary" size="small" type="primary" :loading="uploading" @click="uploadAll">
                  {{ uploading ? '上传中...' : '全部上传' }}
                </van-button>
              </div>
              <van-cell-group inset class="modern-cell-group">
                <van-cell
                  v-for="(file, index) in pendingFiles"
                  :key="index"
                  :title="file.name"
                  :label="formatSize(file.size)"
                  :icon="getFileIcon(file.name)"
                >
                  <template #right-icon>
                    <van-icon name="cross" color="#999" @click.stop="removePending(index)" />
                  </template>
                </van-cell>
              </van-cell-group>
            </div>

            <!-- 上传结果 -->
            <div v-if="uploadResults.length > 0" class="list-section">
              <div class="section-header">
                <span class="section-title">上传结果</span>
                <van-button class="soft-button" size="small" plain @click="uploadResults = []">清除</van-button>
              </div>
              <van-cell-group inset class="modern-cell-group">
                <van-cell
                  v-for="(result, index) in uploadResults"
                  :key="index"
                  :title="result.name"
                  :icon="result.success ? 'success' : 'warning-o'"
                  :icon-color="result.success ? '#07c160' : '#ee0a24'"
                  :label="result.message"
                />
              </van-cell-group>
            </div>

            <!-- 已上传文档 -->
            <div class="list-section">
              <div class="section-header">
                <span class="section-title">
                  已上传文档
                  <van-tag v-if="!loadingDocs" plain type="primary" class="count-tag">{{ documents.length }}</van-tag>
                </span>
                <van-button class="icon-button" size="small" plain icon="replay" @click="loadDocuments" :loading="loadingDocs" />
              </div>
              <van-loading v-if="loadingDocs" size="24px" vertical style="padding:24px 0">加载中</van-loading>
              <van-empty v-else-if="documents.length === 0" description="知识库为空，请上传文档" image-size="80" />
              <van-cell-group v-else inset class="modern-cell-group">
                <van-cell
                  v-for="doc in documents"
                  :key="doc.doc_id"
                  :title="doc.filename"
                  :label="formatDocLabel(doc)"
                  :icon="getFileIcon(doc.filename)"
                >
                  <template #right-icon>
                    <van-icon name="delete-o" color="#ee0a24" size="18" style="padding:4px"
                      @click.stop="confirmDeleteDoc(doc)" />
                  </template>
                </van-cell>
              </van-cell-group>
            </div>

            <!-- 危险操作 -->
            <div class="list-section">
              <van-cell-group inset class="modern-cell-group danger-group">
                <van-cell title="清空我的知识库" label="删除所有已上传的文档"
                  icon="delete-o" icon-color="#ee0a24" is-link @click="confirmClean" />
              </van-cell-group>
            </div>
          </div>
        </van-tab>

        <!-- ── 共享知识库 ── -->
        <van-tab title="共享知识库" name="shared">
          <div class="tab-body">
            <!-- 创建 KB（管理员显示全部选项，普通用户仅个人） -->
            <div class="list-section">
              <van-button class="create-kb-button" block type="primary" icon="plus" @click="showCreateKb = true">
                创建知识库
              </van-button>
              <p class="section-note">{{ createKbNote }}</p>
            </div>

            <!-- KB 列表（按 scope 分组） -->
            <div class="list-section">
              <div class="section-header">
                <span class="section-title">可访问的知识库</span>
                <van-button class="icon-button" size="small" plain icon="replay" @click="loadKbs" :loading="loadingKbs" />
              </div>
              <van-loading v-if="loadingKbs" size="24px" vertical style="padding:24px 0">加载中</van-loading>
              <van-empty v-else-if="kbs.length === 0" description="暂无知识库" image-size="80" />
              <template v-else>
                <div v-for="group in kbGroups" :key="group.scope" class="kb-group">
                  <div class="kb-group-title">{{ group.label }}</div>
                  <van-cell-group inset class="modern-cell-group kb-card-group">
                    <van-cell
                      v-for="kb in group.items"
                      :key="kb.kb_id"
                      :title="kb.name"
                      :label="kbLabel(kb)"
                      is-link
                      @click="openKb(kb)"
                    >
                      <template #right-icon>
                        <div style="display:flex;align-items:center;gap:6px">
                          <van-tag v-if="kb.scope === 'dept' && kb.dept_id" plain type="primary">
                            {{ deptNameOf(kb.dept_id) }}
                          </van-tag>
                          <van-icon
                            v-if="canManageKb(kb)"
                            name="ellipsis"
                            size="20"
                            color="#969799"
                            style="padding: 4px 0 4px 8px"
                            @click.stop="openKbMenu(kb, $event)"
                          />
                        </div>
                      </template>
                    </van-cell>
                  </van-cell-group>
                </div>
              </template>
            </div>
          </div>
        </van-tab>
      </van-tabs>
    </div>

    <!-- 创建知识库弹窗 -->
    <van-dialog
      v-model:show="showCreateKb"
      title="创建知识库"
      show-cancel-button
      :confirm-button-loading="creatingKb"
      :before-close="beforeCloseCreateKb"
    >
      <div style="padding: 16px 16px 8px">
        <van-field
          v-model="newKb.name"
          label="名称"
          placeholder="请输入知识库名称（必填）"
          clearable
        />
        <van-field
          v-model="newKb.description"
          label="描述"
          placeholder="可选描述"
          clearable
        />
        <van-field label="范围">
          <template #input>
            <van-radio-group v-model="newKb.scope" direction="horizontal" style="flex-wrap:wrap;gap:8px">
              <van-radio name="personal">个人（私有）</van-radio>
              <van-radio v-if="isSuperAdmin" name="company">公开</van-radio>
              <van-radio v-if="canCreateDeptKb" name="dept">部门</van-radio>
              <van-radio v-if="isSuperAdmin" name="admin">管理员专属</van-radio>
            </van-radio-group>
          </template>
        </van-field>
      </div>
    </van-dialog>

    <!-- 知识库详情弹窗 -->
    <van-popup v-model:show="showKbDetail" position="bottom" round :style="{ height: '80%' }">
      <div v-if="currentKb" class="kb-detail">
        <div class="kb-detail-header">
          <span class="kb-detail-title">{{ currentKb.name }}</span>
          <van-tag :type="scopeTagType(currentKb.scope)">{{ currentKb.scope }}</van-tag>
        </div>
        <p v-if="currentKb.description" class="kb-detail-desc">{{ currentKb.description }}</p>

        <!-- 查询区域 -->
        <div class="kb-query-area">
          <van-field
            v-model="kbQuery"
            placeholder="在该知识库中检索..."
            :right-icon="queryingKb ? '' : 'search'"
            @keydown.enter="queryKb"
          >
            <template #button>
              <van-button size="small" type="primary" :loading="queryingKb" @click="queryKb">检索</van-button>
            </template>
          </van-field>
        </div>

        <!-- 查询结果 -->
        <div v-if="kbResult" class="kb-result">
          <div class="kb-result-summary">{{ kbResult.summary }}</div>
          <!-- 来源引用 -->
          <div v-if="kbResult.citations && kbResult.citations.length > 0" class="citations">
            <div class="citations-title">来源引用</div>
            <van-cell-group inset>
              <van-cell
                v-for="(c, idx) in kbResult.citations"
                :key="idx"
                :title="c.filename"
                :label="c.chunk_preview"
              >
                <template #right-icon>
                  <van-tag plain>{{ (c.score * 100).toFixed(0) }}%</van-tag>
                </template>
              </van-cell>
            </van-cell-group>
          </div>
        </div>

        <!-- KB 文档列表 -->
        <div class="list-section">
          <div class="section-header">
            <span class="section-title">文档列表</span>
            <van-button v-if="canManageKb(currentKb)" size="small" icon="plus" type="primary" plain @click="triggerKbUpload">上传</van-button>
          </div>
          <input ref="kbFileInputRef" type="file" multiple accept=".pdf,.txt,.md,.docx,.pptx"
            style="display:none" @change="handleKbFileSelect" />
          <van-loading v-if="loadingKbDocs" size="24px" vertical style="padding:16px 0">加载中</van-loading>
          <van-empty v-else-if="kbDocuments.length === 0" description="暂无文档" image-size="60" />
          <van-cell-group v-else inset>
            <van-cell
              v-for="doc in kbDocuments"
              :key="doc.doc_id"
              :title="doc.filename"
              :label="formatDocLabel(doc)"
              :icon="getFileIcon(doc.filename)"
            >
              <template #right-icon>
                <van-icon v-if="canManageKb(currentKb)" name="delete-o" color="#ee0a24" size="18" style="padding:4px"
                  @click.stop="confirmDeleteDoc(doc)" />
              </template>
            </van-cell>
          </van-cell-group>
        </div>
      </div>
    </van-popup>

    <!-- KB 操作菜单 -->
    <van-action-sheet
      v-model:show="showKbActions"
      :actions="kbActionOptions"
      cancel-text="取消"
      @select="onKbAction"
    />

    <!-- 重命名知识库弹窗 -->
    <van-dialog
      v-model:show="showRenameKb"
      title="重命名知识库"
      show-cancel-button
      :confirm-button-loading="renamingKb"
      :before-close="beforeCloseRenameKb"
    >
      <div style="padding: 16px 16px 8px">
        <van-field
          v-model="renameForm.name"
          label="名称"
          placeholder="请输入知识库名称"
          clearable
        />
        <van-field
          v-model="renameForm.description"
          label="描述"
          placeholder="可选描述"
          clearable
        />
      </div>
    </van-dialog>

      <tab-bar />
    </div>

    <template #context>
      <section class="kb-context-card">
        <div class="kb-context-title">
          <h3>资源概览</h3>
          <span>{{ documents.length + kbs.length }}</span>
        </div>
        <div class="kb-context-list">
          <div><span>个人文档</span><strong>{{ documents.length }}</strong></div>
          <div><span>知识库</span><strong>{{ kbs.length }}</strong></div>
          <div><span>待上传</span><strong>{{ pendingFiles.length }}</strong></div>
        </div>
      </section>

      <section class="kb-context-card">
        <div class="kb-context-title">
          <h3>支持格式</h3>
        </div>
        <div class="kb-format-list">
          <span>PDF</span>
          <span>TXT</span>
          <span>MD</span>
          <span>DOCX</span>
          <span>PPTX</span>
        </div>
      </section>

      <section class="kb-context-card">
        <div class="kb-context-title">
          <h3>检索配置</h3>
        </div>
        <div class="kb-context-list">
          <div><span>模式</span><strong>混合检索</strong></div>
          <div><span>重排序</span><strong>开启</strong></div>
          <div><span>来源</span><strong>可追踪</strong></div>
        </div>
      </section>

      <section class="kb-context-card">
        <div class="kb-context-title">
          <h3>危险操作</h3>
        </div>
        <button class="kb-danger-button" type="button" @click="confirmClean">
          清空我的知识库
        </button>
      </section>
    </template>
  </workbench-layout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import axios from 'axios'
import DesktopRail from '../components/DesktopRail.vue'
import TabBar from '../components/TabBar.vue'
import WorkbenchLayout from '../components/WorkbenchLayout.vue'
import { useUserStore } from '../store/user'

const userStore = useUserStore()
const isSuperAdmin = computed(() => userStore.isSuperAdmin)
const isDeptAdmin = computed(() => userStore.isDeptAdmin)
const myDeptId = computed(() => userStore.deptId)
const myDeptName = computed(() => userStore.deptName)
// 兼容旧引用：isAdmin 等价于 super_admin
const isAdmin = isSuperAdmin
// 是否可创建“部门库”：总管理员或部门管理员（部门管理员须已归属部门）
const canCreateDeptKb = computed(() => isSuperAdmin.value || (isDeptAdmin.value && !!myDeptId.value))
const createKbNote = computed(() => {
  if (isSuperAdmin.value) return '总管理员：可创建个人 / 公开 / 部门 / 管理员专属知识库'
  if (canCreateDeptKb.value) return '部门管理员：可创建个人或本部门知识库'
  return '可创建个人（私有）知识库'
})

// 解析某 dept_id 的展示名：本部门用 user_info 的 dept_name，否则回退 id
const deptNameOf = (deptId) => {
  if (!deptId) return ''
  if (deptId === myDeptId.value && myDeptName.value) return myDeptName.value
  return deptId  // 跨部门时仅展示 id（前端不持有全量部门表）
}

// 是否可管理（改名/删）某库
const canManageKb = (kb) => {
  if (!kb) return false
  if (isSuperAdmin.value) return true
  if (kb.scope === 'personal') return kb.owner_id === currentUserUuid.value
  if (kb.scope === 'dept') return isDeptAdmin.value && !!myDeptId.value && kb.dept_id === myDeptId.value
  return false  // company / admin 仅 super_admin
}

const activeTab = ref('personal')
const fileInputRef = ref(null)
const pendingFiles = ref([])
const uploadResults = ref([])
const uploading = ref(false)
const documents = ref([])
const loadingDocs = ref(false)

// ── KB 状态 ──────────────────────────────────────────────────────────────────
const kbs = ref([])
const loadingKbs = ref(false)
const showCreateKb = ref(false)
const creatingKb = ref(false)
const newKb = ref({ name: '', description: '', scope: 'personal' })

const currentKb = ref(null)
const showKbDetail = ref(false)
const kbDocuments = ref([])
const loadingKbDocs = ref(false)
const kbFileInputRef = ref(null)
const kbQuery = ref('')
const queryingKb = ref(false)
const kbResult = ref(null)

// ── KB 操作状态 ────────────────────────────────────────────────────────────
const showKbActions = ref(false)
const actionKb = ref(null)
const showRenameKb = ref(false)
const renameForm = ref({ name: '', description: '' })
const renamingKb = ref(false)

// 按 scope 分组
const KB_GROUP_ORDER = ['personal', 'company', 'dept', 'admin']
const KB_GROUP_LABELS = { personal: '个人', company: '公开', dept: '部门', admin: '管理员专属' }

const kbGroups = computed(() => {
  return KB_GROUP_ORDER
    .map(scope => ({
      scope,
      label: KB_GROUP_LABELS[scope],
      items: kbs.value.filter(kb => kb.scope === scope),
    }))
    .filter(g => g.items.length > 0)
})

const currentUserUuid = computed(() =>
  userStore.userInfo?.uuid || userStore.userInfo?.user_id || ''
)

const kbActionOptions = computed(() => {
  const kb = actionKb.value
  if (!kb || !canManageKb(kb)) return []
  return [
    { name: '重命名', color: '#323233' },
    { name: '删除', color: '#ee0a24' },
  ]
})

const getToken = () => localStorage.getItem('jwt_token') || ''
const authHeader = () => ({ Authorization: `Bearer ${getToken()}` })

// ── 个人文档 ──────────────────────────────────────────────────────────────────

const loadDocuments = async () => {
  if (!getToken()) return
  loadingDocs.value = true
  try {
    const res = await axios.get('/api/vector/list', { headers: authHeader() })
    documents.value = res.data?.data?.documents || []
  } catch {
    showToast('加载文档列表失败')
  } finally {
    loadingDocs.value = false
  }
}

const confirmDeleteDoc = (doc) => {
  showConfirmDialog({
    title: '删除文档',
    message: `确认删除「${doc.filename}」？此操作不可恢复。`,
    confirmButtonColor: '#ee0a24',
  }).then(async () => {
    try {
      await axios.delete(`/api/vector/document/${doc.doc_id}`, { headers: authHeader() })
      showToast('文档已删除')
      if (currentKb.value) {
        await loadKbDocuments(currentKb.value.kb_id)
      } else {
        await loadDocuments()
      }
    } catch (e) {
      showToast('删除失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}

const triggerFileInput = () => fileInputRef.value?.click()
const handleFileSelect = (e) => { addFiles(Array.from(e.target.files)); e.target.value = '' }
const handleDrop = (e) => addFiles(Array.from(e.dataTransfer.files))

const addFiles = (files) => {
  const allowed = ['.pdf', '.txt', '.md', '.docx', '.pptx']
  files.forEach(file => {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!allowed.includes(ext)) { showToast(`不支持的文件类型：${file.name}`); return }
    if (file.size > 20 * 1024 * 1024) { showToast(`文件超过 20MB：${file.name}`); return }
    if (!pendingFiles.value.find(f => f.name === file.name)) pendingFiles.value.push(file)
  })
}

const removePending = (index) => pendingFiles.value.splice(index, 1)

const uploadAll = async () => {
  if (!getToken()) { showToast('请先登录'); return }
  uploading.value = true
  const results = []
  for (const file of pendingFiles.value) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await axios.post('/api/vector/add/single', formData, { headers: authHeader() })
      results.push({ name: file.name, success: true, message: '上传成功，已存入知识库' })
    } catch (e) {
      results.push({ name: file.name, success: false, message: e.response?.data?.message || e.response?.data?.detail || '上传失败' })
    }
  }
  uploadResults.value = [...results, ...uploadResults.value]
  pendingFiles.value = []
  uploading.value = false
  const success = results.filter(r => r.success).length
  showToast(`${success}/${results.length} 个文件上传成功`)
  if (success > 0) await loadDocuments()
}

const confirmClean = () => {
  showConfirmDialog({
    title: '清空知识库',
    message: '将删除你上传的所有文档，此操作不可恢复',
    confirmButtonColor: '#ee0a24',
  }).then(async () => {
    try {
      await axios.delete('/api/vector/clean', { headers: authHeader() })
      showToast('知识库已清空')
      uploadResults.value = []
      await loadDocuments()
    } catch (e) {
      showToast('清空失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}

// ── 共享知识库 ────────────────────────────────────────────────────────────────

const loadKbs = async () => {
  if (!getToken()) return
  loadingKbs.value = true
  try {
    const res = await axios.get('/api/kb/list', { headers: authHeader() })
    kbs.value = res.data?.data?.kbs || []
    // 后端返回当前用户是否管理员
    if (typeof res.data?.data?.is_admin === 'boolean') {
      userStore.isAdmin = res.data.data.is_admin
    }
  } catch {
    showToast('加载知识库列表失败')
  } finally {
    loadingKbs.value = false
  }
}

// beforeClose 用于在确认前执行异步验证，返回 false 阻止关闭
const beforeCloseCreateKb = async (action) => {
  if (action !== 'confirm') return true
  if (!newKb.value.name.trim()) {
    showToast('请输入知识库名称')
    return false
  }
  creatingKb.value = true
  try {
    const payload = { ...newKb.value }
    // 部门管理员创建部门库时，归属到自己的部门；总管理员由后端按需处理
    if (payload.scope === 'dept' && isDeptAdmin.value && myDeptId.value) {
      payload.dept_id = myDeptId.value
    }
    await axios.post('/api/kb', payload, { headers: authHeader() })
    showToast('知识库创建成功')
    newKb.value = { name: '', description: '', scope: 'personal' }
    await loadKbs()
    return true
  } catch (e) {
    showToast('创建失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    return false
  } finally {
    creatingKb.value = false
  }
}

const openKbMenu = (kb, event) => {
  event.stopPropagation()
  actionKb.value = kb
  showKbActions.value = true
}

const onKbAction = (action) => {
  if (action.name === '重命名') {
    renameForm.value = { name: actionKb.value.name, description: actionKb.value.description || '' }
    showRenameKb.value = true
  } else if (action.name === '删除') {
    confirmDeleteKb(actionKb.value)
  }
}

const beforeCloseRenameKb = async (action) => {
  if (action !== 'confirm') return true
  if (!renameForm.value.name.trim()) {
    showToast('知识库名称不能为空')
    return false
  }
  renamingKb.value = true
  try {
    await axios.patch(`/api/kb/${actionKb.value.kb_id}`, renameForm.value, { headers: authHeader() })
    showToast('重命名成功')
    await loadKbs()
    return true
  } catch (e) {
    showToast('重命名失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    return false
  } finally {
    renamingKb.value = false
  }
}

const confirmDeleteKb = (kb) => {
  showConfirmDialog({
    title: '删除知识库',
    message: `确认删除「${kb.name}」？该知识库内所有文档将一并删除，此操作不可恢复。`,
    confirmButtonColor: '#ee0a24',
  }).then(async () => {
    try {
      await axios.delete(`/api/kb/${kb.kb_id}`, { headers: authHeader() })
      showToast('知识库已删除')
      await loadKbs()
    } catch (e) {
      showToast('删除失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
    }
  }).catch(() => {})
}

const openKb = async (kb) => {
  currentKb.value = kb
  kbQuery.value = ''
  kbResult.value = null
  showKbDetail.value = true
  await loadKbDocuments(kb.kb_id)
}

const loadKbDocuments = async (kb_id) => {
  loadingKbDocs.value = true
  try {
    const res = await axios.get(`/api/kb/${kb_id}/documents`, { headers: authHeader() })
    kbDocuments.value = res.data?.data?.documents || []
  } catch {
    showToast('加载文档列表失败')
  } finally {
    loadingKbDocs.value = false
  }
}

const triggerKbUpload = () => kbFileInputRef.value?.click()
const handleKbFileSelect = async (e) => {
  const files = Array.from(e.target.files)
  e.target.value = ''
  if (!currentKb.value) return
  for (const file of files) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await axios.post(`/api/kb/${currentKb.value.kb_id}/documents`, formData, { headers: authHeader() })
      showToast(`${file.name} 上传成功`)
    } catch (err) {
      showToast(`${file.name} 上传失败：` + (err.response?.data?.message || err.response?.data?.detail || '未知错误'))
    }
  }
  await loadKbDocuments(currentKb.value.kb_id)
}

const queryKb = async () => {
  if (!kbQuery.value.trim() || !currentKb.value) return
  queryingKb.value = true
  kbResult.value = null
  try {
    const res = await axios.post(
      `/api/kb/${currentKb.value.kb_id}/query`,
      { query: kbQuery.value },
      { headers: authHeader() }
    )
    kbResult.value = res.data?.data || {}
  } catch (e) {
    showToast('查询失败：' + (e.response?.data?.message || e.response?.data?.detail || '未知错误'))
  } finally {
    queryingKb.value = false
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const formatSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const formatDocLabel = (doc) => {
  const size = formatSize(doc.file_size)
  const chunks = `${doc.chunk_count} 块`
  const time = doc.upload_time
    ? new Date(doc.upload_time).toLocaleString('zh-CN', { hour12: false })
    : ''
  return `${size} · ${chunks}${time ? ' · ' + time : ''}`
}

const getFileIcon = (name) => {
  const ext = name?.split('.').pop()?.toLowerCase()
  const icons = { pdf: 'records', txt: 'description', md: 'description', docx: 'description', pptx: 'photograph' }
  return icons[ext] || 'description'
}

const kbLabel = (kb) => {
  const parts = [`创建者: ${kb.owner_id}`]
  if (kb.description) parts.push(kb.description)
  return parts.join(' · ')
}

const scopeTagType = (scope) => {
  return { personal: 'default', dept: 'primary', company: 'success', admin: 'danger' }[scope] || 'default'
}

const scopeLabel = (scope) => {
  return { personal: '个人', dept: '部门', company: '公开', admin: '管理员' }[scope] || scope
}

onMounted(() => {
  loadDocuments()
  loadKbs()
})
</script>

<style scoped>
.kb-side-header {
  margin-bottom: 14px;
}

.side-eyebrow {
  color: var(--workbench-teal, #178c83);
  font-size: 12px;
  font-weight: 800;
}

.kb-side-header h2 {
  margin: 2px 0 0;
  color: var(--workbench-ink, #16202a);
  font-size: 19px;
  line-height: 1.2;
}

.kb-side-tabs,
.kb-side-section,
.kb-context-card {
  margin-bottom: 14px;
}

.kb-side-tabs {
  display: grid;
  gap: 8px;
}

.kb-side-tabs button,
.kb-side-action,
.kb-danger-button {
  display: flex;
  align-items: center;
  width: 100%;
  border: 0;
  cursor: pointer;
}

.kb-side-tabs button {
  justify-content: space-between;
  gap: 8px;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--workbench-muted, #6b7684);
  font-size: 13px;
  font-weight: 800;
}

.kb-side-tabs button.active,
.kb-side-tabs button:hover {
  border-color: #c8ddf4;
  background: #ffffff;
  color: var(--workbench-primary, #1d6fe8);
  box-shadow: 0 10px 28px rgba(31, 122, 224, 0.08);
}

.kb-side-tabs strong {
  margin-left: auto;
  color: inherit;
}

.kb-side-section {
  padding: 12px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
}

.kb-side-title {
  margin-bottom: 9px;
  color: #8795a5;
  font-size: 12px;
  font-weight: 800;
}

.kb-side-action {
  justify-content: center;
  gap: 6px;
  height: 36px;
  margin-top: 8px;
  border-radius: 10px;
  background: #e8f2ff;
  color: var(--workbench-primary, #1d6fe8);
  font-size: 13px;
  font-weight: 800;
}

.kb-scope-list {
  display: grid;
  gap: 8px;
}

.kb-scope-list span {
  display: flex;
  justify-content: space-between;
  color: var(--workbench-muted, #6b7684);
  font-size: 12px;
}

.kb-scope-list strong {
  color: var(--workbench-ink, #16202a);
}

.kb-context-card {
  padding: 14px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 14px;
  background: #ffffff;
}

.kb-context-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.kb-context-title h3 {
  margin: 0;
  color: var(--workbench-ink, #16202a);
  font-size: 14px;
  line-height: 1.2;
}

.kb-context-title span {
  color: var(--workbench-primary, #1d6fe8);
  font-size: 12px;
  font-weight: 800;
}

.kb-context-list {
  display: grid;
  gap: 8px;
}

.kb-context-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--workbench-muted, #6b7684);
  font-size: 12px;
}

.kb-context-list strong {
  color: var(--workbench-ink, #16202a);
}

.kb-format-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.kb-format-list span {
  padding: 5px 8px;
  border-radius: 999px;
  background: #edf5fb;
  color: #426178;
  font-size: 12px;
  font-weight: 800;
}

.kb-danger-button {
  justify-content: center;
  height: 36px;
  border-radius: 10px;
  background: #fff4f2;
  color: #d74d42;
  font-size: 13px;
  font-weight: 800;
}

.kb-container {
  --page-bg: #f5f7f8;
  --surface: #ffffff;
  --ink: #16202a;
  --muted: #6b7684;
  --line: #dfe7ed;
  --primary: #1d6fe8;
  --teal: #178c83;
  --amber: #b9851d;

  min-height: 100dvh;
  padding-bottom: calc(58px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, #f8faf9 0%, var(--page-bg) 46%, #eef3f5 100%);
  color: var(--ink);
}

@media screen and (min-width: 901px) {
  .kb-container {
    display: flex;
    min-height: 0;
    height: 100%;
    flex-direction: column;
    padding-bottom: 0;
    background: transparent;
  }

  .kb-content {
    min-height: 0;
  }

  .kb-container :deep(.app-tabbar) {
    display: none;
  }
}

.kb-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid rgba(199, 213, 223, 0.72);
  background: rgba(248, 250, 249, 0.94);
  box-shadow: 0 10px 28px rgba(35, 56, 74, 0.06);
  backdrop-filter: blur(16px);
}

.section-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--teal);
  font-size: 12px;
  font-weight: 700;
}

.kb-hero h1 {
  margin: 4px 0 0;
  font-size: 25px;
  line-height: 1.15;
  letter-spacing: 0;
}

.kb-hero-stats {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  align-items: flex-end;
}

.kb-hero-stats span {
  padding: 5px 8px;
  border: 1px solid rgba(102, 127, 150, 0.16);
  border-radius: 999px;
  background: #ffffff;
  color: #536678;
  font-size: 11px;
  font-weight: 750;
  box-shadow: 0 6px 14px rgba(46, 74, 96, 0.06);
}

.kb-content {
  padding-bottom: 8px;
}

.kb-tabs :deep(.van-tabs__wrap) {
  border-bottom: 1px solid rgba(199, 213, 223, 0.65);
  background: rgba(248, 250, 249, 0.96);
}

.kb-tabs :deep(.van-tab) {
  color: #6b7684;
  font-weight: 700;
}

.kb-tabs :deep(.van-tab--active) {
  color: var(--primary);
}

.kb-tabs :deep(.van-tabs__line) {
  background: var(--primary);
}

.tab-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 0;
}

.list-section {
  padding: 0 14px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 2px;
}

.section-title {
  color: #22313d;
  font-size: 14px;
  font-weight: 800;
}

.section-title em {
  margin-left: 4px;
  color: var(--primary);
  font-style: normal;
}

.count-tag {
  margin-left: 6px;
  border-radius: 999px;
}

.upload-area {
  display: flex;
  align-items: center;
  gap: 13px;
  margin: 0 14px;
  padding: 18px 16px;
  border: 1px dashed rgba(29, 111, 232, 0.34);
  border-radius: 8px;
  background: linear-gradient(135deg, #ffffff 0%, #eef7f6 100%);
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.07);
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease;
}

.upload-area:active {
  border-color: rgba(29, 111, 232, 0.56);
  transform: translateY(1px);
}

.upload-icon {
  display: grid;
  place-items: center;
  flex: 0 0 48px;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: #e7f5f2;
  color: var(--teal);
}

.upload-copy {
  min-width: 0;
}

.upload-title {
  margin: 0;
  color: #1c2a35;
  font-size: 16px;
  font-weight: 800;
}

.upload-hint {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.modern-cell-group {
  overflow: hidden;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.06);
}

.modern-cell-group :deep(.van-cell) {
  padding: 13px 14px;
}

.modern-cell-group :deep(.van-cell__title) {
  min-width: 0;
  color: var(--ink);
  font-weight: 700;
}

.modern-cell-group :deep(.van-cell__label) {
  color: var(--muted);
  line-height: 1.45;
}

.danger-group :deep(.van-cell__title) {
  color: #d74d42;
}

.soft-button,
.icon-button {
  border-radius: 8px;
}

.create-kb-button {
  height: 42px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary), #0f4fbf);
  box-shadow: 0 10px 18px rgba(29, 111, 232, 0.18);
}

.section-note {
  margin: 7px 2px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.kb-card-group :deep(.van-cell) {
  align-items: center;
}

.kb-group {
  margin-bottom: 10px;
}

.kb-group-title {
  padding: 8px 18px 5px;
  color: var(--amber);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
}

/* KB detail popup */
.kb-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow-y: auto;
  padding: 18px 16px;
  background: #f5f7f8;
}

.kb-detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-detail-title {
  min-width: 0;
  color: #1c2a35;
  font-size: 20px;
  font-weight: 800;
}

.kb-detail-desc {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.kb-query-area {
  overflow: hidden;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
}

.kb-result {
  padding: 13px;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.06);
}

.kb-result-summary {
  color: #263542;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.citations {
  margin-top: 12px;
}

.citations-title {
  margin-bottom: 8px;
  padding-left: 2px;
  color: var(--amber);
  font-size: 12px;
  font-weight: 800;
}

@media screen and (max-width: 380px) {
  .kb-hero {
    padding: 15px 13px 12px;
  }

  .kb-hero h1 {
    font-size: 22px;
  }

  .list-section {
    padding: 0 10px;
  }

  .upload-area {
    margin: 0 10px;
  }
}
</style>
