<template>
  <div class="ai-chat-page">
    <aside class="desktop-rail" aria-label="主导航">
      <button class="rail-logo" type="button" @click="createNewChat" aria-label="新对话">AI</button>
      <button class="rail-button active" type="button" title="AI问答" aria-label="AI问答" @click="router.push('/aichat')">
        <van-icon name="chat-o" size="21" />
      </button>
      <button class="rail-button" type="button" title="知识库" aria-label="知识库" @click="goToKnowledge">
        <van-icon name="orders-o" size="21" />
      </button>
      <button
        v-if="userStore.isAdmin"
        class="rail-button"
        type="button"
        title="账号管理"
        aria-label="账号管理"
        @click="router.push('/admin/accounts')"
      >
        <van-icon name="manager-o" size="21" />
      </button>
      <button class="rail-button rail-bottom" type="button" title="我的" aria-label="我的" @click="router.push('/my')">
        <van-icon name="user-o" size="21" />
      </button>
    </aside>

    <aside class="history-sidebar" aria-label="历史会话">
      <div class="history-header">
        <div>
          <span class="side-eyebrow">历史上下文</span>
          <h2>会话</h2>
        </div>
        <button class="new-chat-button" type="button" @click="createNewChat">
          <van-icon name="plus" size="14" />
          新对话
        </button>
      </div>

      <label class="history-search">
        <van-icon name="search" size="16" />
        <input v-model="sessionSearch" type="search" placeholder="搜索会话" />
      </label>

      <div class="history-segment" aria-label="会话范围">
        <button
          class="history-segment-button"
          :class="{ active: !showArchivedSessions }"
          type="button"
          @click="switchSessionArchiveView(false)"
        >
          最近
        </button>
        <button
          class="history-segment-button"
          :class="{ active: showArchivedSessions }"
          type="button"
          @click="switchSessionArchiveView(true)"
        >
          归档
        </button>
      </div>

      <div v-if="!isLoggedIn" class="history-empty">
        <van-icon name="contact-o" size="28" />
        <strong>未登录</strong>
        <span>登录后显示会话</span>
      </div>

      <div v-else-if="sessionStore.isLoading && sessionStore.sessions.length === 0" class="history-empty">
        <van-loading size="22" />
        <span>加载中</span>
      </div>

      <div v-else-if="sessionStore.sessions.length === 0" class="history-empty">
        <van-icon name="chat-o" size="28" />
        <strong>{{ showArchivedSessions ? '暂无归档' : '暂无会话' }}</strong>
        <span>{{ showArchivedSessions ? '归档后的会话会显示在这里' : '开始一次新对话' }}</span>
      </div>

      <div v-else class="history-list">
        <template v-for="group in filteredSessionGroups" :key="group.label">
          <div v-if="group.items.length" class="history-group">
            <div class="history-group-label">{{ group.label }}</div>
            <div
              v-for="session in group.items"
              :key="session.session_id"
              class="session-item"
              :class="{ active: isActiveSession(session) }"
            >
              <button class="session-open-area" type="button" @click="selectSession(session)">
                <span class="session-title">{{ getSessionTitle(session) }}</span>
                <span class="session-preview">{{ getSessionPreview(session) }}</span>
                <span class="session-meta">
                  <span>{{ formatSessionTime(session.updated_at || session.created_at) || '时间未知' }}</span>
                  <span>{{ getMessageCount(session) || '继续' }}</span>
                </span>
              </button>
              <button
                class="session-menu-button"
                type="button"
                :aria-label="`管理会话：${getSessionTitle(session)}`"
                @click.stop="openSessionActions(session)"
              >
                <van-icon name="ellipsis" size="18" />
              </button>
            </div>
          </div>
        </template>
      </div>
    </aside>

    <section class="chat-shell">
      <header class="chat-header">
        <div class="header-top">
          <div class="title-block">
            <span class="eyebrow">
              <van-icon name="cluster-o" size="13" />
              智能知识库
            </span>
            <h1>知识问答</h1>
          </div>
          <button class="header-action" type="button" @click="goToSessions">
            <van-icon name="clock-o" size="17" />
            <span>会话</span>
          </button>
        </div>

        <div class="status-row">
          <span class="status-pill">
            <span class="status-dot"></span>
            RAG 已连接
          </span>
          <span class="status-copy">混合检索 · 来源可追踪</span>
        </div>

        <div class="knowledge-strip" aria-label="知识库快捷入口">
          <button
            v-for="source in knowledgeChips"
            :key="source"
            class="knowledge-chip"
            type="button"
            @click="goToKnowledge"
          >
            <van-icon name="description-o" size="13" />
            {{ source }}
          </button>
        </div>
      </header>

      <main class="chat-content">
        <div class="messages-container" ref="messagesContainer">
          <section class="insight-panel">
            <div>
              <span class="panel-kicker">今日工作台</span>
              <h2>把文档变成可追问的答案</h2>
            </div>
            <div class="panel-metrics">
              <span>向量检索</span>
              <span>BM25</span>
              <span>重排序</span>
            </div>
          </section>

          <div
            v-for="(message, index) in messages"
            :key="index"
            :class="['message-row', message.role === 'user' ? 'user-message' : 'ai-message']"
          >
            <div v-if="message.role === 'assistant'" class="message-avatar">AI</div>
            <div class="message-stack">
              <div v-if="message.role === 'assistant'" class="message-meta">
                <span>RAG Assistant</span>
                <span v-if="message.usedRag" class="rag-badge">
                  <van-icon name="search" size="11" />
                  已检索
                </span>
              </div>

              <div class="message-content">
                <div class="markdown-body" v-html="formatMessage(message.content)"></div>
              </div>

              <div
                v-if="message.role === 'assistant' && message.citations && message.citations.length"
                class="citations-section"
              >
                <button class="citations-toggle" type="button" @click="message.showCitations = !message.showCitations">
                  <span>
                    <van-icon name="description-o" size="12" />
                    参考来源 {{ message.citations.length }}
                  </span>
                  <van-icon :name="message.showCitations ? 'arrow-up' : 'arrow-down'" size="12" />
                </button>
                <div v-if="message.showCitations" class="citations-list">
                  <div v-for="(c, ci) in message.citations" :key="ci" class="citation-item">
                    <van-icon name="label-o" size="12" color="#6b7c8f" />
                    <span class="citation-filename">{{ c.filename }}</span>
                    <span class="citation-score">{{ (c.score * 100).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>

              <div
                v-if="message.role === 'assistant' && (message.streaming || message.tokens != null)"
                class="token-usage"
              >
                <van-loading v-if="message.streaming" size="13" />
                <van-icon v-else name="balance-o" size="11" />
                <span v-if="message.elapsed != null">{{ message.elapsed.toFixed(1) }}s</span>
                <span v-if="message.tokens != null">· {{ message.tokens }} tokens</span>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer class="composer-shell">
        <button class="composer-tool" type="button" aria-label="打开知识库" @click="goToKnowledge">
          <van-icon name="notes-o" size="20" />
        </button>
        <van-field
          v-model="userInput"
          rows="1"
          autosize
          type="textarea"
          placeholder="向知识库提问..."
          class="chat-input"
          @keypress.enter.prevent="sendMessage"
        />
        <van-button
          type="primary"
          class="send-button"
          :disabled="isLoading || !userInput.trim()"
          @click="sendMessage"
        >
          <van-icon name="guide-o" size="17" />
        </van-button>
      </footer>
    </section>

    <aside class="context-sidebar" aria-label="上下文面板">
      <section class="context-card">
        <div class="context-card-title">
          <h3>当前会话</h3>
          <span>{{ messages.length }} 条</span>
        </div>
        <p class="current-session-title">{{ currentSessionTitle }}</p>
      </section>

      <section class="context-card">
        <div class="context-card-title">
          <h3>当前知识库</h3>
          <button type="button" @click="goToKnowledge">管理</button>
        </div>
        <div class="context-list">
          <div v-for="source in knowledgeChips" :key="source" class="context-row">
            <span>{{ source }}</span>
            <strong>可用</strong>
          </div>
        </div>
      </section>

      <section class="context-card">
        <div class="context-card-title">
          <h3>参考来源</h3>
          <span>{{ latestCitations.length || 0 }}</span>
        </div>
        <div v-if="latestCitations.length" class="context-list">
          <div v-for="(source, index) in latestCitations" :key="index" class="context-row source-row">
            <span>{{ source.filename || '来源文档' }}</span>
            <strong>{{ source.score != null ? `${(source.score * 100).toFixed(0)}%` : '引用' }}</strong>
          </div>
        </div>
        <p v-else class="context-muted">暂无引用</p>
      </section>

      <section class="context-card">
        <div class="context-card-title">
          <h3>检索配置</h3>
        </div>
        <div class="context-list">
          <div class="context-row"><span>模式</span><strong>混合检索</strong></div>
          <div class="context-row"><span>Top K</span><strong>5</strong></div>
          <div class="context-row"><span>重排序</span><strong>开启</strong></div>
        </div>
      </section>
    </aside>

    <tab-bar />

    <van-action-sheet
      v-model:show="showSessionActions"
      :actions="sessionActionOptions"
      cancel-text="取消"
      @select="onSessionAction"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, onUnmounted, nextTick, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import TabBar from '../components/TabBar.vue';
import { showConfirmDialog, showToast } from 'vant';
import { marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import 'highlight.js/styles/monokai-sublime.css';
import 'highlight.js/lib/common';
import { apiConfig } from '../config/api';
import { useUserStore } from '../store/user';
import { useSessionStore } from '../store/session';

// 从cookie中获取CSRF token
const getCsrfToken = () => {
  const cookieValue = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrftoken='))
    ?.split('=')[1];
  return cookieValue || '';
};

// 聊天消息
const messages = ref([
  { role: 'assistant', content: '你好！我是AI助手，有什么可以帮助你的吗？', citations: [], showCitations: false, usedRag: false }
]);
const knowledgeChips = ['FastAPI 文档', 'LangChain 笔记', '课程资料'];
const userInput = ref('');
const sessionSearch = ref('');
const messagesContainer = ref(null);
const isLoading = ref(false);
const sessionId = ref('');
const hasJumped = ref(false);
const showSessionActions = ref(false);
const actionSession = ref(null);
const showArchivedSessions = ref(false);

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const sessionStore = useSessionStore();
const sessionActionOptions = computed(() => [
  showArchivedSessions.value
    ? { name: '取消归档', value: 'unarchive' }
    : { name: '归档', value: 'archive' },
  { name: '删除', value: 'delete', color: '#d74d42' }
]);

const isLoggedIn = computed(() => Boolean(localStorage.getItem('jwt_token') || userStore.token));
const latestCitations = computed(() => {
  const assistantWithSources = [...messages.value]
    .reverse()
    .find(message => message.role === 'assistant' && message.citations?.length);
  return assistantWithSources?.citations || [];
});
const currentSessionTitle = computed(() => {
  const currentSession = sessionStore.currentSession
    || sessionStore.sessions.find(session => session.session_id === sessionId.value);
  if (currentSession) return getSessionTitle(currentSession);
  return sessionId.value ? '当前会话' : '新对话';
});
const filteredSessionGroups = computed(() => {
  const keyword = sessionSearch.value.trim().toLowerCase();
  const groups = [
    { label: '今天', items: [] },
    { label: '昨天', items: [] },
    { label: '更早', items: [] }
  ];

  sessionStore.sessions
    .filter(session => {
      if (!keyword) return true;
      return [
        getSessionTitle(session),
        getSessionPreview(session),
        formatSessionTime(session.updated_at || session.created_at)
      ].some(value => String(value || '').toLowerCase().includes(keyword));
    })
    .forEach(session => {
      const label = getSessionDateGroup(session.updated_at || session.created_at);
      const group = groups.find(item => item.label === label) || groups[2];
      group.items.push(session);
    });

  return groups;
});

// 配置marked使用marked-highlight插件
marked.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
    return hljs.highlight(code, { language }).value;
  }
}));

// 格式化消息内容（支持Markdown和代码高亮）
const formatMessage = (content) => {
  if (!content) return '';
  try {
    // 使用marked解析Markdown，并用DOMPurify清理HTML
    const parsed = marked(content, {
      breaks: true,
      gfm: true,
      headerIds: false,
      mangle: false
    });
    const sanitized = DOMPurify.sanitize(parsed);
    return sanitized;
  } catch (error) {
    console.error('Markdown解析错误:', error);
    return content;
  }
};

// 生成耗时实时计时器（同一时刻只有最后一条回答在流式）
let tickTimer = null;
const stopTick = () => {
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null; }
};
const startTick = (msg) => {
  stopTick();
  tickTimer = setInterval(() => {
    if (msg && msg.streaming) {
      msg.elapsed = (Date.now() - msg.startTime) / 1000;
    } else {
      stopTick();
    }
  }, 100);
};
onUnmounted(stopTick);

// 发送消息
const sendMessage = async () => {
  if (!userInput.value.trim() || isLoading.value) return;
  
  // 检查是否登录（以实际 token 为准，避免 isLogin 持久化导致误判）
  const token = localStorage.getItem('jwt_token') || userStore.token;
  if (!token) {
    showToast('请先登录');
    router.push('/login');
    return;
  }
  
  // 添加用户消息
  const userMessage = userInput.value.trim();
  messages.value.push({ role: 'user', content: userMessage });
  userInput.value = '';
  
  // 添加AI消息占位
  messages.value.push({ role: 'assistant', content: '', citations: [], showCitations: false, usedRag: false, tokens: null, streaming: true, startTime: Date.now(), elapsed: 0 });
  // 启动实时计时（拿响应式代理引用，保证 elapsed 变化能触发更新）
  startTick(messages.value[messages.value.length - 1]);

  // 滚动到底部
  await nextTick();
  scrollToBottom();
  
  // 发送请求
  isLoading.value = true;
  try {
    await fetchAIResponse(userMessage);
  } catch (error) {
    console.error('Error fetching AI response:', error);
    // 更新最后一条消息为错误信息
    messages.value[messages.value.length - 1].content = `发生错误: ${error.message || '请检查网络连接和API设置'}`;
  } finally {
    isLoading.value = false;
    // 兜底：停止计时与转圈，并把耗时定格为最终值
    stopTick();
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.streaming = false;
      if (lastMsg.startTime) lastMsg.elapsed = (Date.now() - lastMsg.startTime) / 1000;
    }
    await nextTick();
    scrollToBottom();
  }
};

// 获取AI响应（使用SSE）
const fetchAIResponse = async (userMessage) => {
  try {
    // 确保使用正确的相对路径，通过Vite代理访问
    const url = '/api/agent/query/stream';
    // 从localStorage获取token
    const token = localStorage.getItem('jwt_token') || userStore.token;
    // console.log('发送AI请求到:', url);
    // console.log('使用的token:', token);
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        session_id: sessionId.value || undefined,
        query: userMessage
      })
    });
    
    if (!response.ok) {
      if (response.status === 401) {
        userStore.clearAuth();
        showToast('登录已过期，请重新登录');
        router.push('/login');
        return;
      }
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }
    
    // 处理SSE流
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let aiResponse = '';
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (!data) continue;
        
        try {
          const json = JSON.parse(data);
          
          switch (json.type) {
            case 'step':
              if (json.data?.tool === 'rag_summary_tools') {
                const lastMsg = messages.value[messages.value.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.usedRag = true;
                }
              }
              break;
            case 'response':
              const content = json.content || '';
              if (content) {
                aiResponse += content;
                
                // 逐字符显示打字机效果
                const displayContent = messages.value[messages.value.length - 1].content || '';
                const remainingContent = aiResponse.substring(displayContent.length);
                
                for (const char of remainingContent) {
                  messages.value[messages.value.length - 1].content += char;
                  await nextTick();
                  scrollToBottom();
                  // 控制打字速度，每个字符延迟8ms
                  await new Promise(resolve => setTimeout(resolve, 8));
                }
              }
              // 保存会话ID（不立即跳转，避免中断SSE）
              if (json.session_id && typeof json.session_id === 'string' && json.session_id.trim()) {
                sessionId.value = json.session_id;
              }
              break;
            case 'usage': {
              // 流式 token 估算，实时跳动（转圈期间显示，结束时校准）
              const lastMsg = messages.value[messages.value.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.tokens = json.tokens;
              }
              break;
            }
            case 'done':
              // 保存会话ID并在所有数据接收完成后跳转
              if (json.session_id && typeof json.session_id === 'string' && json.session_id.trim()) {
                sessionId.value = json.session_id;
                // 如果当前路由没有sessionId参数，跳转到带sessionId的路由
                if (!route.params.sessionId) {
                  router.push(`/aichat/${json.session_id}`);
                }
                await loadSidebarSessions();
              }
              // 将检索来源附加到最后一条 AI 消息
              if (json.citations && json.citations.length) {
                const lastMsg = messages.value[messages.value.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.citations = json.citations;
                }
              }
              // 结束：停止转圈，用精确 token 总数定格
              {
                const lastMsg = messages.value[messages.value.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  if (json.tokens != null) lastMsg.tokens = json.tokens;
                  lastMsg.streaming = false;
                }
              }
              break;
            case 'error':
              throw new Error(json.content || 'API错误');
              break;
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      }
    }
  }
  
  // 如果没有收到任何内容
  if (!aiResponse) {
    messages.value[messages.value.length - 1].content = '抱歉，我无法生成回复。请检查API设置或稍后再试。';
  }
  } catch (error) {
    console.error('Fetch error:', error);
    throw error;
  }
};

// 跳转到会话管理页面
const goToSessions = () => {
  router.push('/sessions');
};

// 跳转到知识库页面
const goToKnowledge = () => {
  router.push('/knowledge');
};

const getUserId = () => userStore.userInfo?.uuid || userStore.userInfo?.id || userStore.userInfo?.user_id;

const loadSidebarSessions = async () => {
  const token = localStorage.getItem('jwt_token') || userStore.token;
  if (!token) return;

  if (!userStore.userInfo) {
    const result = await userStore.getUserInfoDetail();
    if (!result.success) return;
  }

  const userId = getUserId();
  if (userId) {
    await sessionStore.getUserSessions(userId, { archived: showArchivedSessions.value });
  }
};

const switchSessionArchiveView = async (archived) => {
  if (showArchivedSessions.value === archived) return;
  showArchivedSessions.value = archived;
  sessionSearch.value = '';
  await loadSidebarSessions();
};

const createNewChat = () => {
  sessionStore.requestNewChat();
  resetChatState();
  if (route.path !== '/aichat') {
    router.push('/aichat');
  }
};

const selectSession = (session) => {
  if (!session?.session_id || session.session_id === sessionId.value) return;
  router.push(`/aichat/${session.session_id}`);
};

const openSessionActions = (session) => {
  actionSession.value = session;
  showSessionActions.value = true;
};

const onSessionAction = async (action) => {
  showSessionActions.value = false;
  if (!actionSession.value?.session_id) return;

  if (action.value === 'archive' || action.name === '归档') {
    await updateSessionArchiveState(actionSession.value, true);
    return;
  }

  if (action.value === 'unarchive' || action.name === '取消归档') {
    await updateSessionArchiveState(actionSession.value, false);
    return;
  }

  if (action.value === 'delete' || action.name === '删除') {
    await deleteSessionFromHistory(actionSession.value);
  }
};

const updateSessionArchiveState = async (session, archived) => {
  const result = await sessionStore.setSessionArchived(session.session_id, archived);
  if (result.success) {
    showToast(archived ? '会话已归档' : '会话已取消归档');
    if (archived && session.session_id === sessionId.value) {
      sessionStore.requestNewChat();
      resetChatState();
      router.push('/aichat');
    }
    await loadSidebarSessions();
  } else {
    showToast(result.message || '操作失败');
  }
};

const deleteSessionFromHistory = async (session) => {
  try {
    await showConfirmDialog({
      title: '删除会话',
      message: `确认删除「${getSessionTitle(session)}」？此操作不可恢复。`
    });
  } catch {
    return;
  }

  const deletingCurrent = session.session_id === sessionId.value;
  const result = await sessionStore.deleteSession(session.session_id);
  if (result.success) {
    showToast('会话已删除');
    if (deletingCurrent) {
      sessionStore.requestNewChat();
      resetChatState();
      router.push('/aichat');
    }
    await loadSidebarSessions();
  } else {
    showToast(result.message || '删除失败');
  }
};

const isActiveSession = (session) => session?.session_id && session.session_id === sessionId.value;

const getSessionTitle = (session) => {
  if (session?.title) return session.title;
  if (session?.history?.length) {
    const firstMessage = session.history[0]?.[0] || '';
    return firstMessage.length > 24 ? `${firstMessage.substring(0, 24)}...` : firstMessage;
  }
  return '新会话';
};

const getSessionPreview = (session) => {
  if (session?.history?.length) {
    const lastPair = session.history[session.history.length - 1];
    const preview = lastPair?.[0] || lastPair?.[1] || '';
    return preview.length > 42 ? `${preview.substring(0, 42)}...` : preview;
  }
  return session?.updated_at ? '点击继续这段对话' : '继续对话';
};

const getMessageCount = (session) => {
  const count = Array.isArray(session?.history) ? session.history.length : 0;
  return count > 0 ? `${count} 轮` : '';
};

const formatSessionTime = (timeString) => {
  if (!timeString) return '';
  try {
    const date = new Date(timeString);
    const now = new Date();
    const sameYear = date.getFullYear() === now.getFullYear();
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      ...(sameYear ? {} : { year: 'numeric' }),
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  } catch (error) {
    return timeString;
  }
};

const getSessionDateGroup = (timeString) => {
  if (!timeString) return '更早';
  const date = new Date(timeString);
  if (Number.isNaN(date.getTime())) return '更早';

  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);

  if (date >= startOfToday) return '今天';
  if (date >= startOfYesterday) return '昨天';
  return '更早';
};

// 滚动到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
};

// 监听消息变化，自动滚动
watch(messages, () => {
  nextTick(() => {
    scrollToBottom();
  });
}, { deep: true });

// 重置为空白新会话状态（点击「新对话」或路由无 sessionId 时调用）
const resetChatState = () => {
  messages.value = [
    { role: 'assistant', content: '你好！我是AI助手，有什么可以帮助你的吗？', citations: [], showCitations: false, usedRag: false }
  ];
  sessionId.value = '';
  sessionStore.setCurrentSession(null);
};

// 根据当前路由同步聊天显示：有 sessionId 则加载历史，否则重置为空白会话
const syncWithRoute = async () => {
  const sessionIdParam = route.params.sessionId;
  if (sessionIdParam) {
    if (sessionId.value === sessionIdParam) return;
    // 立即设置 sessionId，避免用户在异步加载完成前发消息时创建新会话
    sessionId.value = sessionIdParam;
    try {
      const result = await sessionStore.getSession(sessionIdParam);
      if (result.success && sessionStore.currentSession) {
        loadSessionHistory(sessionStore.currentSession);
      } else {
        showToast('加载会话历史失败');
      }
    } catch (error) {
      console.error('加载会话历史失败:', error);
      showToast('加载会话历史失败');
    }
  } else {
    // 进入基础 /aichat：仅在显式「新对话」/登录时重置为干净界面；
    // 切换到别的栏目再切回时保留最近这次的问答界面
    if (sessionStore.newChatRequested) {
      sessionStore.newChatRequested = false;
      resetChatState();
    }
  }
};

// /aichat 已开启 keep-alive，切换 tab 返回时组件实例与消息会被缓存保留；
// watcher 负责同组件内 /aichat ↔ /aichat/:id 的路由切换同步
watch(() => route.fullPath, (newFullPath, oldFullPath) => {
  if (newFullPath === oldFullPath) return;
  if (!route.path.startsWith('/aichat')) return;
  syncWithRoute();
});

onMounted(async () => {
  await syncWithRoute();
  await loadSidebarSessions();
  scrollToBottom();
});

// keep-alive 缓存的组件再次被激活时（切回 tab）同步一次路由状态
onActivated(async () => {
  await syncWithRoute();
  await loadSidebarSessions();
  scrollToBottom();
});

// 加载会话历史
const loadSessionHistory = (session) => {
  messages.value = [];
  if (session.history && session.history.length > 0) {
    session.history.forEach(([userMsg, aiMsg]) => {
      messages.value.push({ role: 'user', content: userMsg });
      messages.value.push({ role: 'assistant', content: aiMsg, citations: [], showCitations: false, usedRag: false });
    });
  }
  sessionId.value = session.session_id;
};
</script>

<style scoped>
.ai-chat-page {
  --page-bg: #f5f7f8;
  --surface: #ffffff;
  --surface-soft: #f7fafc;
  --ink: #16202a;
  --muted: #6b7684;
  --line: #dfe7ed;
  --primary: #1d6fe8;
  --primary-deep: #0f4fbf;
  --teal: #178c83;
  --amber: #b9851d;
  --shadow: 0 18px 50px rgba(20, 42, 68, 0.1);

  display: grid;
  grid-template-columns: 76px minmax(280px, 320px) minmax(0, 1fr) minmax(260px, 300px);
  width: 100vw;
  height: 100dvh;
  min-height: 100vh;
  padding-bottom: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(238, 243, 247, 0.9)),
    radial-gradient(circle at 36% 0%, rgba(29, 111, 232, 0.13), transparent 34%),
    var(--page-bg);
  color: var(--ink);
  overflow: hidden;
}

.desktop-rail,
.history-sidebar,
.context-sidebar {
  min-height: 0;
  border-color: var(--line);
}

.desktop-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 18px 12px;
  border-right: 1px solid var(--line);
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
  color: var(--primary);
}

.rail-bottom {
  margin-top: auto;
}

.history-sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 18px 14px;
  border-right: 1px solid var(--line);
  background: rgba(250, 252, 254, 0.92);
}

.history-header,
.context-card-title,
.session-meta,
.status-row,
.knowledge-strip,
.message-row,
.message-meta,
.panel-metrics,
.composer-shell,
.citation-item,
.citations-toggle,
.context-row,
.new-chat-button,
.history-search {
  display: flex;
  align-items: center;
}

.history-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.side-eyebrow {
  color: var(--teal);
  font-size: 12px;
  font-weight: 800;
}

.history-header h2 {
  margin: 2px 0 0;
  font-size: 19px;
  line-height: 1.2;
}

.new-chat-button {
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
  height: 36px;
  padding: 0 12px;
  border: 0;
  border-radius: 10px;
  background: var(--primary);
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.history-search {
  gap: 8px;
  height: 40px;
  margin-bottom: 12px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #ffffff;
  color: var(--muted);
}

.history-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  font-size: 13px;
}

.history-search input::placeholder {
  color: #9aa8b4;
}

.history-segment {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 14px;
  padding: 4px;
  border: 1px solid #d9e4ec;
  border-radius: 12px;
  background: #edf3f8;
}

.history-segment-button {
  min-height: 32px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #667486;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.history-segment-button.active {
  background: #ffffff;
  color: var(--primary);
  box-shadow: 0 6px 18px rgba(30, 82, 140, 0.1);
}

.history-list {
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.history-group {
  margin-top: 12px;
}

.history-group:first-child {
  margin-top: 0;
}

.history-group-label {
  margin: 0 2px 8px;
  color: #8795a5;
  font-size: 12px;
  font-weight: 800;
}

.session-item {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 30px;
  gap: 4px;
  align-items: flex-start;
  width: 100%;
  margin-bottom: 8px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: inherit;
}

.session-item.active {
  border-color: #c8ddf4;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(31, 122, 224, 0.1);
}

.session-item:hover {
  background: #ffffff;
}

.session-open-area,
.session-menu-button {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.session-open-area {
  min-width: 0;
  padding: 11px 0 11px 12px;
  text-align: left;
}

.session-menu-button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin: 8px 8px 0 0;
  border-radius: 8px;
  color: #7d8b99;
}

.session-menu-button:hover {
  background: #eef5ff;
  color: var(--primary);
}

.session-title,
.session-preview {
  display: block;
  min-width: 0;
  overflow: hidden;
}

.session-title {
  margin-bottom: 6px;
  color: var(--ink);
  font-size: 14px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-preview {
  color: var(--muted);
  display: -webkit-box;
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.session-meta {
  justify-content: space-between;
  gap: 10px;
  margin-top: 9px;
  color: #8b99a8;
  font-size: 11px;
}

.history-empty {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 8px;
  flex: 1;
  min-height: 160px;
  border: 1px dashed #d4e0e8;
  border-radius: 14px;
  color: #8b99a8;
  text-align: center;
}

.history-empty strong {
  color: #526174;
}

.chat-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
}

.chat-header {
  padding: 18px 26px 14px;
  background: rgba(255, 255, 255, 0.82);
  border-bottom: 1px solid rgba(199, 213, 223, 0.72);
  backdrop-filter: blur(16px);
}

.header-top {
  justify-content: space-between;
  gap: 20px;
}

.title-block {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--teal);
  font-size: 13px;
  font-weight: 800;
  line-height: 1.2;
}

.title-block h1 {
  margin: 5px 0 0;
  font-size: 28px;
  line-height: 1.15;
  letter-spacing: 0;
  color: var(--ink);
}

.header-action,
.knowledge-chip,
.composer-tool,
.citations-toggle {
  border: 0;
  font: inherit;
  cursor: pointer;
}

.header-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 8px 10px;
  border: 1px solid rgba(29, 111, 232, 0.16);
  border-radius: 8px;
  background: #ffffff;
  color: var(--primary);
  font-size: 13px;
  font-weight: 650;
  box-shadow: 0 6px 16px rgba(25, 72, 122, 0.08);
}

.status-row {
  gap: 8px;
  margin-top: 13px;
  min-width: 0;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 5px 8px;
  border: 1px solid rgba(23, 140, 131, 0.2);
  border-radius: 999px;
  background: #e7f5f2;
  color: #0e6d66;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #18b394;
  box-shadow: 0 0 0 3px rgba(24, 179, 148, 0.16);
}

.status-copy {
  min-width: 0;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-strip {
  gap: 8px;
  margin-top: 13px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}

.knowledge-strip::-webkit-scrollbar {
  display: none;
}

.knowledge-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  min-height: 30px;
  max-width: 168px;
  padding: 0 10px;
  border: 1px solid rgba(102, 127, 150, 0.16);
  border-radius: 8px;
  background: #ffffff;
  color: #355066;
  font-size: 12px;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(46, 74, 96, 0.05);
}

.chat-content {
  min-height: 0;
  overflow: hidden;
}

.messages-container {
  height: 100%;
  overflow-y: auto;
  padding: 24px 32px 32px;
}

.insight-panel {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  min-height: 88px;
  margin-bottom: 24px;
  padding: 18px 20px;
  border: 1px solid #d4e5f1;
  border-radius: 14px;
  background: linear-gradient(90deg, #ffffff 0%, #f0fbfa 100%);
  box-shadow: 0 12px 34px rgba(39, 73, 94, 0.07);
}

.panel-kicker {
  color: var(--amber);
  font-size: 12px;
  font-weight: 800;
}

.insight-panel h2 {
  margin: 5px 0 0;
  color: #1c2a35;
  font-size: 18px;
  line-height: 1.25;
  letter-spacing: 0;
}

.panel-metrics {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
  min-width: 118px;
}

.panel-metrics span {
  padding: 7px 9px;
  border: 1px solid #e3ebf1;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  color: #536678;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.message-row {
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.message-avatar {
  display: grid;
  place-items: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: #123451;
  color: #ffffff;
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 8px 16px rgba(18, 52, 81, 0.16);
}

.message-stack {
  max-width: min(82%, 760px);
  min-width: 0;
}

.user-message {
  justify-content: flex-end;
}

.user-message .message-stack {
  max-width: min(76%, 720px);
}

.message-meta {
  gap: 6px;
  margin: 0 0 5px 1px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 650;
}

.message-content {
  overflow: hidden;
  padding: 14px 16px;
  border-radius: 14px;
  word-break: break-word;
}

.ai-message .message-content {
  border: 1px solid rgba(199, 213, 223, 0.76);
  background: rgba(255, 255, 255, 0.94);
  color: #263542;
  box-shadow: 0 12px 34px rgba(39, 73, 94, 0.08);
}

.user-message .message-content {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-deep) 100%);
  color: #ffffff;
  box-shadow: 0 10px 20px rgba(29, 111, 232, 0.18);
}

.rag-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 7px;
  border-radius: 999px;
  background: #e7f5f2;
  color: #0e6d66;
  font-size: 10px;
  font-weight: 750;
}

.citations-section {
  margin-top: 8px;
  overflow: hidden;
  border: 1px solid rgba(199, 213, 223, 0.75);
  border-radius: 10px;
  background: rgba(250, 252, 252, 0.92);
}

.citations-toggle {
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 34px;
  padding: 0 10px;
  background: transparent;
  color: #607083;
  font-size: 11px;
  font-weight: 750;
}

.citations-toggle span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.citations-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0 10px 9px;
}

.citation-item {
  gap: 6px;
  min-width: 0;
  padding: 6px 7px;
  border-radius: 6px;
  background: #ffffff;
  color: #526476;
  font-size: 11px;
}

.token-usage {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  color: #94a3b4;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.citation-filename {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-score {
  flex-shrink: 0;
  color: var(--amber);
  font-weight: 800;
}

.composer-shell {
  gap: 8px;
  padding: 14px 24px;
  border-top: 1px solid rgba(199, 213, 223, 0.72);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 -10px 28px rgba(35, 56, 74, 0.06);
  backdrop-filter: blur(16px);
}

.composer-tool {
  display: grid;
  place-items: center;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  border: 1px solid rgba(102, 127, 150, 0.18);
  border-radius: 12px;
  background: #ffffff;
  color: #38556e;
}

.chat-input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(102, 127, 150, 0.16);
  border-radius: 12px;
  background: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.chat-input :deep(.van-field__control) {
  max-height: 104px;
  min-height: 22px;
  color: var(--ink);
  font-size: 14px;
  line-height: 22px;
}

.chat-input :deep(.van-field__control::placeholder) {
  color: #9aa8b4;
  opacity: 1;
}

.chat-input :deep(.van-field__body) {
  align-items: center;
}

.chat-input :deep(.van-cell) {
  padding: 8px 10px;
}

.send-button {
  flex: 0 0 48px;
  width: 48px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-deep) 100%);
  box-shadow: 0 10px 18px rgba(29, 111, 232, 0.2);
}

.context-sidebar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  padding: 18px 16px;
  border-left: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.76);
}

.context-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
}

.context-card-title {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.context-card-title h3 {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.2;
}

.context-card-title span,
.context-card-title button {
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  font-weight: 800;
}

.context-card-title button {
  cursor: pointer;
}

.current-session-title,
.context-muted {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}

.context-list {
  display: flex;
  flex-direction: column;
}

.context-row {
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  padding: 9px 0;
  border-top: 1px solid #edf2f6;
  color: #526174;
  font-size: 13px;
}

.context-row:first-child {
  border-top: 0;
}

.context-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-row strong {
  flex-shrink: 0;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
}

.source-row strong {
  color: var(--amber);
}

:deep(.app-tabbar.van-tabbar) {
  display: none;
}

.send-button.van-button--disabled {
  background: #c8d4df;
  color: #ffffff;
  box-shadow: none;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
  line-height: 1.68;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(pre) {
  margin: 10px 0;
  padding: 12px;
  overflow-x: auto;
  border-radius: 8px;
  background-color: #16202a;
  color: #dce7ef;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background-color: transparent;
  color: inherit;
}

.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 5px;
  background-color: rgba(22, 32, 42, 0.08);
  color: #1c4768;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 0.9em;
}

.user-message .markdown-body :deep(code) {
  background-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 18px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
  line-height: 1.55;
}

.markdown-body :deep(a) {
  color: var(--primary);
  text-decoration: none;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 12px 0 8px;
  color: #1c2a35;
  font-weight: 800;
  letter-spacing: 0;
}

.markdown-body :deep(h1) {
  font-size: 1.34em;
}

.markdown-body :deep(h2) {
  font-size: 1.2em;
}

.markdown-body :deep(h3) {
  font-size: 1.08em;
}

.markdown-body :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 10px;
  border-left: 3px solid var(--teal);
  border-radius: 0 6px 6px 0;
  background-color: #eef7f6;
  color: #536678;
}

.markdown-body :deep(hr) {
  margin: 14px 0;
  border: 0;
  border-top: 1px solid var(--line);
}

.markdown-body :deep(img) {
  max-width: 100%;
  margin: 8px 0;
  border-radius: 6px;
}

.markdown-body :deep(table) {
  width: 100%;
  margin: 10px 0;
  border-collapse: collapse;
  font-size: 12px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 7px;
  border: 1px solid var(--line);
  text-align: left;
}

.markdown-body :deep(th) {
  background-color: #eef3f5;
  font-weight: 800;
}

@media screen and (max-width: 1180px) {
  .ai-chat-page {
    grid-template-columns: 72px minmax(260px, 300px) minmax(0, 1fr);
  }

  .context-sidebar {
    display: none;
  }
}

@media screen and (max-width: 900px) {
  .ai-chat-page {
    display: flex;
    flex-direction: column;
    width: 100%;
    padding-bottom: calc(58px + env(safe-area-inset-bottom));
    background: linear-gradient(180deg, #f8faf9 0%, var(--page-bg) 42%, #eef3f5 100%);
  }

  .desktop-rail,
  .history-sidebar,
  .context-sidebar {
    display: none;
  }

  .chat-shell {
    display: flex;
    flex: 1;
    min-height: 0;
    flex-direction: column;
  }

  .chat-header {
    flex-shrink: 0;
    padding: 18px 18px 12px;
    background: rgba(248, 250, 249, 0.94);
    box-shadow: 0 10px 28px rgba(35, 56, 74, 0.06);
  }

  .title-block h1 {
    font-size: 25px;
  }

  .chat-content {
    flex: 1;
  }

  .messages-container {
    padding: 14px 14px 12px;
  }

  .insight-panel {
    min-height: 0;
    margin-bottom: 16px;
    padding: 13px 14px;
    border-radius: 8px;
  }

  .insight-panel h2 {
    font-size: 15px;
  }

  .panel-metrics span {
    padding: 4px 6px;
    border: 0;
    border-radius: 6px;
    font-size: 10px;
  }

  .message-avatar {
    flex-basis: 30px;
    width: 30px;
    height: 30px;
    border-radius: 8px;
  }

  .message-stack,
  .user-message .message-stack {
    max-width: 86%;
  }

  .message-content {
    padding: 12px 13px;
    border-radius: 8px;
  }

  .composer-shell {
    flex-shrink: 0;
    padding: 10px 12px 12px;
    background: rgba(248, 250, 249, 0.96);
  }

  .composer-tool {
    flex-basis: 40px;
    width: 40px;
    height: 40px;
    border-radius: 8px;
  }

  .send-button {
    flex-basis: 42px;
    width: 42px;
    height: 40px;
    border-radius: 8px;
  }

  :deep(.app-tabbar.van-tabbar) {
    display: flex;
  }
}

@media screen and (max-width: 380px) {
  .chat-header {
    padding: 15px 13px 10px;
  }

  .title-block h1 {
    font-size: 22px;
  }

  .messages-container {
    padding: 12px 10px 10px;
  }

  .message-stack,
  .user-message .message-stack {
    max-width: 86%;
  }

  .insight-panel {
    flex-direction: column;
  }

  .panel-metrics {
    justify-content: flex-start;
  }
}
</style>
