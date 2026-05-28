<template>
  <div class="ai-chat-page">
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
              <span v-if="message.tokens != null">{{ message.tokens }} tokens</span>
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

    <tab-bar />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import TabBar from '../components/TabBar.vue';
import { showToast } from 'vant';
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
const messagesContainer = ref(null);
const isLoading = ref(false);
const sessionId = ref('');
const hasJumped = ref(false);

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const sessionStore = useSessionStore();

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
  messages.value.push({ role: 'assistant', content: '', citations: [], showCitations: false, usedRag: false, tokens: null, streaming: true });
  
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
    // 兜底：无论成功或异常，结束后都停止最后一条消息的转圈
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') lastMsg.streaming = false;
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
    resetChatState();
  }
};

// /aichat 关闭了 keep-alive，每次进入页面组件都会重新挂载；
// 但 vue-router 在同组件 /aichat ↔ /aichat/:id 切换时会复用实例，故仍需 watcher
watch(() => route.fullPath, (newFullPath, oldFullPath) => {
  if (newFullPath === oldFullPath) return;
  if (!route.path.startsWith('/aichat')) return;
  syncWithRoute();
});

onMounted(() => {
  syncWithRoute();
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
  --surface-soft: #eef5f5;
  --ink: #16202a;
  --muted: #6b7684;
  --line: #dfe7ed;
  --primary: #1d6fe8;
  --primary-deep: #0f4fbf;
  --teal: #178c83;
  --amber: #b9851d;

  display: flex;
  flex-direction: column;
  height: 100dvh;
  min-height: 100vh;
  padding-bottom: calc(58px + env(safe-area-inset-bottom));
  background:
    linear-gradient(180deg, #f8faf9 0%, var(--page-bg) 42%, #eef3f5 100%);
  color: var(--ink);
  overflow: hidden;
}

.chat-header {
  flex-shrink: 0;
  padding: 18px 18px 12px;
  background: rgba(248, 250, 249, 0.94);
  border-bottom: 1px solid rgba(199, 213, 223, 0.72);
  box-shadow: 0 10px 28px rgba(35, 56, 74, 0.06);
  backdrop-filter: blur(16px);
}

.header-top,
.status-row,
.knowledge-strip,
.message-row,
.message-meta,
.panel-metrics,
.composer-shell,
.citation-item,
.citations-toggle {
  display: flex;
  align-items: center;
}

.header-top {
  justify-content: space-between;
  gap: 14px;
}

.title-block {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--teal);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.2;
}

.title-block h1 {
  margin: 4px 0 0;
  font-size: 25px;
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
  margin-top: 12px;
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
  margin-top: 12px;
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
  max-width: 142px;
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
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.messages-container {
  height: 100%;
  overflow-y: auto;
  padding: 14px 14px 12px;
}

.insight-panel {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 13px 14px;
  border: 1px solid rgba(31, 79, 117, 0.09);
  border-radius: 8px;
  background: linear-gradient(135deg, #ffffff 0%, #eef7f6 100%);
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.07);
}

.panel-kicker {
  color: var(--amber);
  font-size: 11px;
  font-weight: 750;
}

.insight-panel h2 {
  margin: 3px 0 0;
  color: #1c2a35;
  font-size: 15px;
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
  padding: 4px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.78);
  color: #536678;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.message-row {
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.message-avatar {
  display: grid;
  place-items: center;
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: #123451;
  color: #ffffff;
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 8px 16px rgba(18, 52, 81, 0.16);
}

.message-stack {
  max-width: min(88%, 560px);
  min-width: 0;
}

.user-message {
  justify-content: flex-end;
}

.user-message .message-stack {
  max-width: min(80%, 520px);
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
  padding: 12px 13px;
  border-radius: 8px;
  word-break: break-word;
}

.ai-message .message-content {
  border: 1px solid rgba(199, 213, 223, 0.76);
  background: rgba(255, 255, 255, 0.94);
  color: #263542;
  box-shadow: 0 10px 24px rgba(39, 73, 94, 0.08);
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
  border-radius: 8px;
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
  flex-shrink: 0;
  gap: 8px;
  padding: 10px 12px 12px;
  border-top: 1px solid rgba(199, 213, 223, 0.72);
  background: rgba(248, 250, 249, 0.96);
  box-shadow: 0 -10px 28px rgba(35, 56, 74, 0.06);
  backdrop-filter: blur(16px);
}

.composer-tool {
  display: grid;
  place-items: center;
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(102, 127, 150, 0.18);
  border-radius: 8px;
  background: #ffffff;
  color: #38556e;
}

.chat-input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(102, 127, 150, 0.16);
  border-radius: 8px;
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
  flex: 0 0 42px;
  width: 42px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-deep) 100%);
  box-shadow: 0 10px 18px rgba(29, 111, 232, 0.2);
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
