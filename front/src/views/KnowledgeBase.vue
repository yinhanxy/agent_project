<template>
  <div class="kb-container">
    <van-nav-bar title="知识库" fixed />

    <div class="kb-content">
      <!-- 模式切换 -->
      <van-tabs v-model:active="activeTab" sticky offset-top="46">

        <!-- ── 个人文档 ── -->
        <van-tab title="个人文档" name="personal">
          <div class="tab-body">
            <!-- 上传区域 -->
            <div class="upload-area" @click="triggerFileInput" @dragover.prevent @drop.prevent="handleDrop">
              <van-icon name="plus" size="36" color="#1989fa" />
              <p class="upload-title">点击或拖拽上传文件</p>
              <p class="upload-hint">支持 PDF、TXT、MD、DOCX、PPTX，单文件最大 20MB</p>
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
                <span class="section-title">待上传 ({{ pendingFiles.length }})</span>
                <van-button size="small" type="primary" :loading="uploading" @click="uploadAll">
                  {{ uploading ? '上传中...' : '全部上传' }}
                </van-button>
              </div>
              <van-cell-group inset>
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
                <van-button size="small" plain @click="uploadResults = []">清除</van-button>
              </div>
              <van-cell-group inset>
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
                  <van-tag v-if="!loadingDocs" plain type="primary" style="margin-left:6px">{{ documents.length }}</van-tag>
                </span>
                <van-button size="small" plain icon="replay" @click="loadDocuments" :loading="loadingDocs" />
              </div>
              <van-loading v-if="loadingDocs" size="24px" vertical style="padding:24px 0">加载中</van-loading>
              <van-empty v-else-if="documents.length === 0" description="知识库为空，请上传文档" image-size="80" />
              <van-cell-group v-else inset>
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
              <van-cell-group inset>
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
              <van-button block type="primary" icon="plus" @click="showCreateKb = true">
                创建知识库
              </van-button>
              <p style="font-size:12px;color:#999;margin:6px 4px 0">
                {{ isAdmin ? '管理员：可创建个人/公开/部门/管理员专属知识库' : '可创建个人（私有）或公开知识库' }}
              </p>
            </div>

            <!-- KB 列表（按 scope 分组） -->
            <div class="list-section">
              <div class="section-header">
                <span class="section-title">可访问的知识库</span>
                <van-button size="small" plain icon="replay" @click="loadKbs" :loading="loadingKbs" />
              </div>
              <van-loading v-if="loadingKbs" size="24px" vertical style="padding:24px 0">加载中</van-loading>
              <van-empty v-else-if="kbs.length === 0" description="暂无知识库" image-size="80" />
              <template v-else>
                <div v-for="group in kbGroups" :key="group.scope" class="kb-group">
                  <div class="kb-group-title">{{ group.label }}</div>
                  <van-cell-group inset>
                    <van-cell
                      v-for="kb in group.items"
                      :key="kb.kb_id"
                      :title="kb.name"
                      :label="kbLabel(kb)"
                      is-link
                      @click="openKb(kb)"
                    >
                      <template #right-icon>
                        <van-icon
                          name="ellipsis"
                          size="20"
                          color="#969799"
                          style="padding: 4px 0 4px 8px"
                          @click.stop="openKbMenu(kb, $event)"
                        />
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
              <van-radio name="company">公开</van-radio>
              <van-radio v-if="isAdmin" name="dept">部门</van-radio>
              <van-radio v-if="isAdmin" name="admin">管理员专属</van-radio>
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
            <van-button size="small" icon="plus" type="primary" plain @click="triggerKbUpload">上传</van-button>
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
                <van-icon name="delete-o" color="#ee0a24" size="18" style="padding:4px"
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
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import axios from 'axios'
import TabBar from '../components/TabBar.vue'
import { useUserStore } from '../store/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

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
  const actions = [{ name: '重命名', color: '#323233' }]
  if (isAdmin.value || actionKb.value?.owner_id === currentUserUuid.value) {
    actions.push({ name: '删除', color: '#ee0a24' })
  }
  return actions
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
      showToast('删除失败：' + (e.response?.data?.detail || '未知错误'))
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
      results.push({ name: file.name, success: false, message: e.response?.data?.detail || '上传失败' })
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
      showToast('清空失败：' + (e.response?.data?.detail || '未知错误'))
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
    await axios.post('/api/kb', newKb.value, { headers: authHeader() })
    showToast('知识库创建成功')
    newKb.value = { name: '', description: '', scope: 'personal' }
    await loadKbs()
    return true
  } catch (e) {
    showToast('创建失败：' + (e.response?.data?.detail || '未知错误'))
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
    showToast('重命名失败：' + (e.response?.data?.detail || '未知错误'))
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
      showToast('删除失败：' + (e.response?.data?.detail || '未知错误'))
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
      showToast(`${file.name} 上传失败：` + (err.response?.data?.detail || '未知错误'))
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
    showToast('查询失败：' + (e.response?.data?.detail || '未知错误'))
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
.kb-container { min-height: 100vh; background: #f7f8fa; }
.kb-content { padding-top: 46px; padding-bottom: 60px; }
.tab-body { display: flex; flex-direction: column; gap: 12px; padding: 12px 0; }
.list-section { padding: 0 16px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 4px;
}
.section-title { font-size: 14px; font-weight: 500; color: #323233; }
.upload-area {
  margin: 0 16px;
  border: 2px dashed #1989fa;
  border-radius: 12px;
  background: #f0f7ff;
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.upload-area:active { background: #daeeff; }
.upload-title { font-size: 15px; color: #1989fa; font-weight: 500; }
.upload-hint { font-size: 12px; color: #999; text-align: center; }

/* KB 详情弹窗 */
.kb-detail { padding: 16px; height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.kb-detail-header { display: flex; align-items: center; gap: 8px; }
.kb-detail-title { font-size: 18px; font-weight: 600; color: #323233; }
.kb-detail-desc { font-size: 13px; color: #666; margin: 0; }
.kb-query-area { }
.kb-result { background: #f7f8fa; border-radius: 8px; padding: 12px; }
.kb-result-summary { font-size: 14px; color: #323233; line-height: 1.6; white-space: pre-wrap; }
.citations { margin-top: 12px; }
.citations-title { font-size: 13px; font-weight: 500; color: #666; margin-bottom: 8px; padding-left: 4px; }
.kb-group { margin-bottom: 8px; }
.kb-group-title {
  font-size: 12px;
  font-weight: 600;
  color: #969799;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 8px 20px 4px;
}
</style>
