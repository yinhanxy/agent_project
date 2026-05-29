<template>
  <workbench-layout page-class="sessions-workbench" sidebar-label="历史会话" context-label="会话上下文">
    <template #rail>
      <desktop-rail />
    </template>

    <template #sidebar>
      <div class="desktop-side-header">
        <span class="side-eyebrow">历史上下文</span>
        <h2>会话</h2>
      </div>

      <label class="side-search">
        <van-icon name="search" size="16" />
        <input v-model="sessionSearch" type="search" placeholder="搜索会话" />
      </label>

      <div class="session-segment" aria-label="会话范围">
        <button
          class="session-segment-button"
          :class="{ active: !showArchivedSessions }"
          type="button"
          @click="switchSessionArchiveView(false)"
        >
          最近
        </button>
        <button
          class="session-segment-button"
          :class="{ active: showArchivedSessions }"
          type="button"
          @click="switchSessionArchiveView(true)"
        >
          归档
        </button>
      </div>

      <button class="side-new-button" type="button" @click="createNewSession">
        <van-icon name="plus" size="14" />
        新对话
      </button>

      <div v-if="sessionStore.isLoading" class="side-empty">
        <van-loading size="22" />
        <span>加载中</span>
      </div>

      <div v-else-if="filteredSessions.length === 0" class="side-empty">
        <van-icon name="chat-o" size="26" />
        <strong>暂无匹配会话</strong>
        <span>换个关键词试试</span>
      </div>

      <div v-else class="side-session-list">
        <button
          v-for="session in filteredSessions"
          :key="session.session_id"
          class="side-session-item"
          :class="{ active: sessionStore.currentSession?.session_id === session.session_id }"
          type="button"
          @click="selectSession(session)"
        >
          <span class="side-session-title">{{ session.title || getSessionTitle(session) }}</span>
          <span class="side-session-preview">{{ getSessionPreview(session) }}</span>
          <span class="side-session-meta">
            <span>{{ formatSessionTime(session.created_at) || '时间未知' }}</span>
            <span>{{ getMessageCount(session) || '继续' }}</span>
          </span>
        </button>
      </div>
    </template>

    <section class="desktop-sessions-main">
      <header class="desktop-hero">
        <div>
          <span class="section-eyebrow">
            <van-icon name="clock-o" size="13" />
            历史上下文
          </span>
          <h1>会话管理</h1>
        </div>
        <van-button class="hero-action" type="primary" icon="plus" @click="createNewSession">
          新对话
        </van-button>
      </header>

      <div class="sessions-content desktop-scroll">
        <div class="summary-panel">
          <div>
            <span class="panel-kicker">检索记录</span>
            <strong>{{ sessionStore.sessions.length }}</strong>
            <span>条会话</span>
          </div>
          <div>
            <span class="panel-kicker">当前状态</span>
            <strong>{{ sessionStore.currentSession ? '已选择' : '空白' }}</strong>
            <span>上下文</span>
          </div>
        </div>

        <div v-if="sessionStore.isLoading" class="loading">
          <van-loading type="spinner" color="#1d6fe8" />
          <p>加载中...</p>
        </div>

        <div v-else-if="filteredSessions.length === 0" class="empty-sessions">
          <div class="empty-icon">
            <van-icon name="chat-o" size="34" />
          </div>
          <h2>暂无会话记录</h2>
          <p>开始一次新对话后，这里会保存你的追问线索。</p>
          <van-button class="empty-action" type="primary" icon="plus" @click="createNewSession">
            新对话
          </van-button>
        </div>

        <div v-else class="session-card-list">
          <article
            v-for="session in filteredSessions"
            :key="session.session_id"
            class="session-card"
            :class="{ active: sessionStore.currentSession?.session_id === session.session_id }"
            @click="selectSession(session)"
          >
            <div class="session-icon">
              <van-icon name="comment-o" size="18" />
            </div>
            <div class="session-main">
              <div class="session-title-row">
                <h2>{{ session.title || getSessionTitle(session) }}</h2>
                <van-icon name="arrow" size="14" />
              </div>
              <p>{{ getSessionPreview(session) }}</p>
              <div class="session-meta">
                <span>
                  <van-icon name="underway-o" size="12" />
                  {{ formatSessionTime(session.created_at) || '时间未知' }}
                </span>
                <span v-if="getMessageCount(session) > 0">
                  {{ getMessageCount(session) }} 轮
                </span>
                <span v-else>继续对话</span>
              </div>
            </div>
            <button class="archive-action" type="button" @click.stop="updateSessionArchiveState(session)">
              {{ showArchivedSessions ? '取消归档' : '归档' }}
            </button>
            <button class="delete-action" type="button" @click.stop="deleteSession(session.session_id)">
              删除
            </button>
          </article>
        </div>
      </div>
    </section>

    <template #context>
      <section class="context-card">
        <div class="context-card-title">
          <h3>会话统计</h3>
          <span>{{ sessionStore.sessions.length }}</span>
        </div>
        <div class="context-list">
          <div class="context-row"><span>当前筛选</span><strong>{{ filteredSessions.length }} 条</strong></div>
          <div class="context-row"><span>当前状态</span><strong>{{ sessionStore.currentSession ? '已选择' : '空白' }}</strong></div>
          <div class="context-row"><span>入口</span><strong>AI 问答</strong></div>
        </div>
      </section>

      <section class="context-card">
        <div class="context-card-title">
          <h3>当前会话</h3>
        </div>
        <p class="context-muted">{{ currentSessionSummary }}</p>
      </section>

      <section class="context-card">
        <div class="context-card-title">
          <h3>快捷操作</h3>
        </div>
        <button class="context-action" type="button" @click="createNewSession">
          <van-icon name="plus" size="14" />
          新对话
        </button>
      </section>
    </template>

    <template #mobile>
      <div class="sessions-container app-section-page">
        <header class="section-hero">
          <div>
            <span class="section-eyebrow">
              <van-icon name="clock-o" size="13" />
              历史上下文
            </span>
            <h1>会话管理</h1>
          </div>
          <van-button class="hero-action" type="primary" icon="plus" @click="createNewSession">
            新对话
          </van-button>
        </header>

        <div class="sessions-content">
          <div class="session-segment" aria-label="会话范围">
            <button
              class="session-segment-button"
              :class="{ active: !showArchivedSessions }"
              type="button"
              @click="switchSessionArchiveView(false)"
            >
              最近
            </button>
            <button
              class="session-segment-button"
              :class="{ active: showArchivedSessions }"
              type="button"
              @click="switchSessionArchiveView(true)"
            >
              归档
            </button>
          </div>

          <div class="summary-panel">
            <div>
              <span class="panel-kicker">检索记录</span>
              <strong>{{ sessionStore.sessions.length }}</strong>
              <span>条会话</span>
            </div>
            <div>
              <span class="panel-kicker">当前状态</span>
              <strong>{{ sessionStore.currentSession ? '已选择' : '空白' }}</strong>
              <span>上下文</span>
            </div>
          </div>

          <div v-if="sessionStore.isLoading" class="loading">
            <van-loading type="spinner" color="#1d6fe8" />
            <p>加载中...</p>
          </div>

          <div v-else-if="filteredSessions.length === 0" class="empty-sessions">
            <div class="empty-icon">
              <van-icon name="chat-o" size="34" />
            </div>
            <h2>{{ showArchivedSessions ? '暂无归档会话' : '暂无会话记录' }}</h2>
            <p>{{ showArchivedSessions ? '归档后的会话会显示在这里，可以随时恢复。' : '开始一次新对话后，这里会保存你的追问线索。' }}</p>
            <van-button class="empty-action" type="primary" icon="plus" @click="createNewSession">
              新对话
            </van-button>
          </div>

          <div v-else class="session-card-list">
            <article
              v-for="session in filteredSessions"
              :key="session.session_id"
              class="session-card"
              :class="{ active: sessionStore.currentSession?.session_id === session.session_id }"
              @click="selectSession(session)"
            >
              <div class="session-icon">
                <van-icon name="comment-o" size="18" />
              </div>
              <div class="session-main">
                <div class="session-title-row">
                  <h2>{{ session.title || getSessionTitle(session) }}</h2>
                  <van-icon name="arrow" size="14" />
                </div>
                <p>{{ getSessionPreview(session) }}</p>
                <div class="session-meta">
                  <span>
                    <van-icon name="underway-o" size="12" />
                    {{ formatSessionTime(session.created_at) || '时间未知' }}
                  </span>
                  <span v-if="getMessageCount(session) > 0">
                    {{ getMessageCount(session) }} 轮
                  </span>
                  <span v-else>继续对话</span>
                </div>
              </div>
              <button class="archive-action" type="button" @click.stop="updateSessionArchiveState(session)">
                {{ showArchivedSessions ? '取消归档' : '归档' }}
              </button>
              <button class="delete-action" type="button" @click.stop="deleteSession(session.session_id)">
                删除
              </button>
            </article>
          </div>
        </div>

        <tab-bar />
      </div>
    </template>
  </workbench-layout>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { showToast } from 'vant';
import DesktopRail from '../components/DesktopRail.vue';
import TabBar from '../components/TabBar.vue';
import WorkbenchLayout from '../components/WorkbenchLayout.vue';
import { useSessionStore } from '../store/session';
import { useUserStore } from '../store/user';

const router = useRouter();
const route = useRoute();
const sessionStore = useSessionStore();
const userStore = useUserStore();
const sessionSearch = ref('');
const showArchivedSessions = ref(false);

const filteredSessions = computed(() => {
  const keyword = sessionSearch.value.trim().toLowerCase();
  if (!keyword) return sessionStore.sessions;

  return sessionStore.sessions.filter(session => {
    return [
      session.title || getSessionTitle(session),
      getSessionPreview(session),
      formatSessionTime(session.created_at)
    ].some(value => String(value || '').toLowerCase().includes(keyword));
  });
});

const currentSessionSummary = computed(() => {
  const session = sessionStore.currentSession;
  if (!session) return '尚未选择会话。可以从左侧列表进入历史对话，或直接开启新对话。';
  return `${session.title || getSessionTitle(session)} · ${getMessageCount(session)} 轮对话`;
});


// 监听路由变化，确保每次访问会话管理页面时自动刷新会话列表
watch(() => route.path, async (newPath) => {
  if (newPath === '/sessions') {
    await loadSessions();
  }
});

// 加载会话列表
const loadSessions = async () => {
  // 检查是否登录
  if (!userStore.getLoginStatus) {
    showToast('请先登录');
    router.push('/login?redirect=/sessions');
    return;
  }
  
  // 获取用户ID（假设从用户信息中获取）
  if (!userStore.userInfo) {
    const result = await userStore.getUserInfoDetail();
    if (!result.success) {
      showToast('获取用户信息失败');
      return;
    }
  }
  
  if (userStore.userInfo) {

    
    // 尝试获取用户ID，支持不同的字段名
    let userId = userStore.userInfo.uuid || userStore.userInfo.id || userStore.userInfo.user_id;
    
    if (userId) {
      await sessionStore.getUserSessions(userId, { archived: showArchivedSessions.value });
    } else {
      // 显示详细的错误信息
      showToast('获取用户ID失败，请检查用户信息结构');
      console.error('用户信息中没有找到ID字段:', userStore.userInfo);
    }
  } else {
    showToast('获取用户信息失败');
  }
};

// 组件挂载时获取会话列表
onMounted(async () => {
  await loadSessions();
});

// 获取会话标题（使用第一条消息作为标题）
const getSessionTitle = (session) => {
  if (session.history && session.history.length > 0) {
    const firstMessage = session.history[0][0]; // 第一条用户消息
    return firstMessage.length > 20 ? firstMessage.substring(0, 20) + '...' : firstMessage;
  }
  return '新会话';
};

const switchSessionArchiveView = async (archived) => {
  if (showArchivedSessions.value === archived) return;
  showArchivedSessions.value = archived;
  sessionSearch.value = '';
  await loadSessions();
};

const getSessionPreview = (session) => {
  if (session.history && session.history.length > 0) {
    const lastPair = session.history[session.history.length - 1];
    const preview = lastPair?.[0] || lastPair?.[1] || '';
    return preview.length > 42 ? preview.substring(0, 42) + '...' : preview;
  }
  return '点击继续这段对话';
};

const getMessageCount = (session) => {
  return Array.isArray(session.history) ? session.history.length : 0;
};

// 格式化会话时间
const formatSessionTime = (timeString) => {
  if (!timeString) return '';
  try {
    const date = new Date(timeString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (error) {
    return timeString;
  }
};

// 选择会话
const selectSession = (session) => {
  // 跳转到带会话ID的路由
  router.push(`/aichat/${session.session_id}`);
};

// 删除会话
const deleteSession = async (sessionId) => {

  
  const result = await sessionStore.deleteSession(sessionId);
  if (result.success) {
    showToast('会话删除成功');
  } else {
    showToast(result.message || '删除失败');
  }
};

const updateSessionArchiveState = async (session) => {
  const nextArchived = !showArchivedSessions.value;
  const result = await sessionStore.setSessionArchived(session.session_id, nextArchived);
  if (result.success) {
    showToast(nextArchived ? '会话已归档' : '会话已取消归档');
    await loadSessions();
  } else {
    showToast(result.message || '操作失败');
  }
};

// 开始新对话：清空当前会话引用并跳转到空白聊天页
const createNewSession = () => {
  sessionStore.requestNewChat();
  router.push('/aichat');
};
</script>

<style scoped>
.desktop-sessions-main {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
}

.desktop-hero {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(199, 213, 223, 0.72);
  background: rgba(248, 250, 249, 0.94);
  box-shadow: 0 10px 28px rgba(35, 56, 74, 0.06);
}

.desktop-scroll {
  min-height: 0;
}

.desktop-side-header {
  margin-bottom: 14px;
}

.side-eyebrow {
  color: var(--workbench-teal, #178c83);
  font-size: 12px;
  font-weight: 800;
}

.desktop-side-header h2 {
  margin: 2px 0 0;
  color: var(--workbench-ink, #16202a);
  font-size: 19px;
  line-height: 1.2;
}

.side-search,
.side-new-button,
.side-session-meta,
.context-card-title,
.context-row,
.context-action {
  display: flex;
  align-items: center;
}

.side-search {
  gap: 8px;
  height: 40px;
  margin-bottom: 10px;
  padding: 0 12px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 10px;
  background: #ffffff;
  color: var(--workbench-muted, #6b7684);
}

.side-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--workbench-ink, #16202a);
  font-size: 13px;
}

.session-segment {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 12px;
  padding: 4px;
  border: 1px solid #d9e4ec;
  border-radius: 12px;
  background: #edf3f8;
}

.session-segment-button {
  min-height: 32px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #667486;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.session-segment-button.active {
  background: #ffffff;
  color: var(--workbench-primary, #1d6fe8);
  box-shadow: 0 6px 18px rgba(30, 82, 140, 0.1);
}

.side-new-button {
  justify-content: center;
  gap: 5px;
  width: 100%;
  height: 38px;
  margin-bottom: 12px;
  border: 0;
  border-radius: 10px;
  background: var(--workbench-primary, #1d6fe8);
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.side-session-list {
  min-height: 0;
  max-height: calc(100dvh - 138px);
  overflow-y: auto;
  padding-right: 2px;
}

.side-session-item {
  display: block;
  width: 100%;
  margin-bottom: 8px;
  padding: 11px 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.side-session-item.active,
.side-session-item:hover {
  border-color: #c8ddf4;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(31, 122, 224, 0.1);
}

.side-session-title,
.side-session-preview {
  display: block;
  min-width: 0;
  overflow: hidden;
}

.side-session-title {
  margin-bottom: 6px;
  color: var(--workbench-ink, #16202a);
  font-size: 14px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.side-session-preview {
  color: var(--workbench-muted, #6b7684);
  display: -webkit-box;
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.side-session-meta {
  justify-content: space-between;
  gap: 10px;
  margin-top: 9px;
  color: #8b99a8;
  font-size: 11px;
}

.side-empty {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 8px;
  min-height: 160px;
  border: 1px dashed #d4e0e8;
  border-radius: 14px;
  color: #8b99a8;
  text-align: center;
}

.context-card {
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--workbench-line, #dfe7ed);
  border-radius: 14px;
  background: #ffffff;
}

.context-card-title {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.context-card-title h3 {
  margin: 0;
  color: var(--workbench-ink, #16202a);
  font-size: 14px;
  line-height: 1.2;
}

.context-card-title span {
  color: var(--workbench-primary, #1d6fe8);
  font-size: 12px;
  font-weight: 800;
}

.context-list {
  display: grid;
  gap: 8px;
}

.context-row {
  justify-content: space-between;
  gap: 12px;
  color: var(--workbench-muted, #6b7684);
  font-size: 12px;
}

.context-row strong {
  color: var(--workbench-ink, #16202a);
}

.context-muted {
  margin: 0;
  color: var(--workbench-muted, #6b7684);
  font-size: 13px;
  line-height: 1.55;
}

.context-action {
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 38px;
  border: 0;
  border-radius: 10px;
  background: #e8f2ff;
  color: var(--workbench-primary, #1d6fe8);
  font-weight: 800;
  cursor: pointer;
}

.sessions-container {
  --page-bg: #f5f7f8;
  --surface: #ffffff;
  --ink: #16202a;
  --muted: #6b7684;
  --line: #dfe7ed;
  --primary: #1d6fe8;
  --teal: #178c83;
  --amber: #b9851d;

  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  padding-bottom: calc(58px + env(safe-area-inset-bottom));
  background: linear-gradient(180deg, #f8faf9 0%, var(--page-bg) 46%, #eef3f5 100%);
  color: var(--ink);
}

.section-hero {
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

.section-hero h1 {
  margin: 4px 0 0;
  font-size: 25px;
  line-height: 1.15;
  letter-spacing: 0;
}

.hero-action {
  flex-shrink: 0;
  height: 38px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary), #0f4fbf);
  box-shadow: 0 10px 18px rgba(29, 111, 232, 0.18);
}

.sessions-content {
  flex: 1;
  padding: 14px;
  overflow-y: auto;
}

.summary-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.summary-panel > div {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(31, 79, 117, 0.09);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.07);
}

.panel-kicker {
  display: block;
  color: var(--amber);
  font-size: 11px;
  font-weight: 750;
}

.summary-panel strong {
  display: block;
  margin-top: 3px;
  color: #1c2a35;
  font-size: 18px;
  line-height: 1.2;
}

.summary-panel span:last-child {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
}

.loading p {
  margin-top: 16px;
  color: var(--muted);
}

.empty-sessions {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  padding: 26px;
  text-align: center;
  border: 1px solid rgba(199, 213, 223, 0.72);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.07);
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 8px;
  background: #e7f5f2;
  color: var(--teal);
}

.empty-sessions h2 {
  margin: 14px 0 4px;
  font-size: 18px;
  letter-spacing: 0;
}

.empty-sessions p {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}

.empty-action {
  border-radius: 8px;
}

.session-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-card {
  display: grid;
  grid-template-columns: 38px 1fr auto auto;
  gap: 10px;
  align-items: flex-start;
  padding: 13px;
  border: 1px solid rgba(199, 213, 223, 0.78);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.07);
}

.session-card.active {
  border-color: rgba(29, 111, 232, 0.34);
  background: linear-gradient(135deg, #ffffff 0%, #eef5ff 100%);
}

.session-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #123451;
  color: #ffffff;
}

.session-main {
  min-width: 0;
}

.session-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.session-title-row h2 {
  flex: 1;
  overflow: hidden;
  margin: 0;
  color: var(--ink);
  font-size: 15px;
  line-height: 1.35;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-title-row .van-icon {
  flex-shrink: 0;
  color: #8aa0b2;
}

.session-main p {
  display: -webkit-box;
  overflow: hidden;
  margin: 5px 0 8px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.session-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #789;
  font-size: 11px;
}

.session-meta span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.archive-action,
.delete-action {
  align-self: center;
  min-width: 44px;
  height: 30px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.archive-action {
  border: 1px solid rgba(29, 111, 232, 0.22);
  background: #f0f6ff;
  color: #1d6fe8;
}

.delete-action {
  border: 1px solid rgba(215, 77, 66, 0.24);
  background: #fff7f6;
  color: #d74d42;
}

@media screen and (max-width: 380px) {
  .section-hero {
    padding: 15px 13px 12px;
  }

  .sessions-content {
    padding: 12px 10px;
  }

  .session-card {
    grid-template-columns: 34px 1fr;
  }

  .archive-action,
  .delete-action {
    grid-column: 2;
    justify-self: flex-start;
  }
}

</style>
