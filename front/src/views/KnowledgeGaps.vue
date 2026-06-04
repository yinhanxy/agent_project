<template>
  <workbench-layout page-class="gap-workbench" single-content>
    <template #rail>
      <desktop-rail />
    </template>

    <div class="gap-container">
      <van-nav-bar title="知识缺口" fixed />

      <van-tabs v-model:active="activeStatus" @change="loadGaps" sticky offset-top="46px">
        <van-tab title="全部" name="" />
        <van-tab title="待处理" name="pending" />
        <van-tab title="已查看" name="reviewed" />
        <van-tab title="已解决" name="resolved" />
        <van-tab title="已忽略" name="ignored" />
      </van-tabs>

      <div class="gap-content">
        <van-loading v-if="loading" size="24px" vertical style="padding:32px 0">加载中</van-loading>
        <van-empty v-else-if="gaps.length === 0" description="暂无知识缺口" image-size="80" />

        <van-cell-group v-else inset>
          <van-cell
            v-for="g in gaps"
            :key="g.id"
            :title="g.title"
            :label="g.question"
          >
            <template #value>
              <div class="gap-meta">
                <div class="gap-tags">
                  <van-tag :type="statusType(g.status)">{{ statusLabel(g.status) }}</van-tag>
                  <van-tag plain type="primary">{{ g.category }}</van-tag>
                </div>
                <van-button size="mini" plain type="primary" @click="openAction(g)">改状态</van-button>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </div>

      <van-action-sheet
        v-model:show="showAction"
        :actions="actions"
        cancel-text="取消"
        close-on-click-action
        @select="onSelectStatus"
      />
    </div>
  </workbench-layout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { showToast } from 'vant'
import WorkbenchLayout from '../components/WorkbenchLayout.vue'
import DesktopRail from '../components/DesktopRail.vue'

const gaps = ref([])
const loading = ref(false)
const activeStatus = ref('')
const showAction = ref(false)
const current = ref(null)

const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('jwt_token')}` })

const STATUS_LABEL = { pending: '待处理', reviewed: '已查看', resolved: '已解决', ignored: '已忽略' }
const STATUS_TYPE = { pending: 'warning', reviewed: 'primary', resolved: 'success', ignored: 'default' }
const statusLabel = (s) => STATUS_LABEL[s] || s
const statusType = (s) => STATUS_TYPE[s] || 'default'

const actions = [
  { name: '标记已查看', value: 'reviewed' },
  { name: '标记已解决', value: 'resolved' },
  { name: '标记已忽略', value: 'ignored' },
  { name: '重置为待处理', value: 'pending' },
]

async function loadGaps() {
  loading.value = true
  try {
    const params = activeStatus.value ? { status: activeStatus.value } : {}
    const res = await axios.get('/api/knowledge-gaps', { params, headers: authHeader() })
    gaps.value = res.data?.data?.gaps || []
  } catch (e) {
    showToast('加载失败，请重试')
  } finally {
    loading.value = false
  }
}

function openAction(g) {
  current.value = g
  showAction.value = true
}

async function onSelectStatus(action) {
  if (!current.value) return
  try {
    await axios.patch(
      `/api/knowledge-gaps/${current.value.id}`,
      { status: action.value },
      { headers: authHeader() }
    )
    showToast('状态已更新')
    await loadGaps()
  } catch (e) {
    const code = e?.response?.status
    showToast(code === 403 ? '无权修改' : '更新失败')
  } finally {
    current.value = null
  }
}

onMounted(loadGaps)
</script>

<style scoped>
.gap-container { min-height: 100%; }
.gap-content { padding: 12px 0 32px; }
.gap-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.gap-tags { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
</style>
