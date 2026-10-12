<template>
  <div class="chat-container">
    <div class="chat-window">
      <!-- 顶部：客服信息 + 操作 -->
      <div class="chat-header">
        <div class="service-avatar">客</div>
        <div class="service-info">
          <div class="service-name">数码优选 · 智能客服</div>
          <div class="service-status"><span class="online-dot"></span>在线 · 秒回 · 人工可转接</div>
        </div>
        <div class="header-actions">
          <button class="ghost-btn" @click="switchUser" title="切换测试用户">👤 {{ currentUser }}</button>
          <button class="ghost-btn" @click="clearChat" title="清空当前会话">🧹 清空</button>
          <button class="ghost-btn" @click="endSession" :disabled="isLoading" title="结束会话并记录偏好">结束会话</button>
        </div>
      </div>

      <!-- 消息区 -->
      <div class="message-list" ref="messageListRef">
        <!-- 空状态：欢迎语 + 快捷提问 -->
        <div v-if="messages.length === 0" class="empty-state">
          <div class="welcome-card">
            <div class="welcome-title">你好，我是数码商城智能客服 👋</div>
            <p class="welcome-sub">可以问我商品参数、订单物流、优惠活动、推荐、比价或售后问题</p>
          </div>
          <div class="quick-questions">
            <div v-for="q in quickQuestions" :key="q" class="quick-item" @click="sendQuery(q)">{{ q }}</div>
          </div>
        </div>

        <!-- 消息气泡 -->
        <div v-for="(msg, index) in messages" :key="index" :class="['message-row', msg.role]">
          <div class="msg-avatar">{{ msg.role === 'user' ? '我' : '客' }}</div>
          <div class="msg-body">
            <div class="message-bubble" v-html="renderMarkdown(msg.content)"></div>
            <!-- 工单号高亮 -->
            <div v-if="ticketNoOf(msg.content)" class="ticket-chip">
              🎫 已转人工 · 工单号 <code>{{ ticketNoOf(msg.content) }}</code>
            </div>
          </div>
        </div>

        <!-- 正在输入 -->
        <div v-if="isLoading" class="message-row assistant">
          <div class="msg-avatar">客</div>
          <div class="msg-body">
            <div class="message-bubble typing">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <textarea
          v-model="inputQuery"
          rows="1"
          placeholder="请输入您的问题，Enter 发送，Shift+Enter 换行"
          @keydown.enter.prevent="handleEnter"
          :disabled="isLoading"
        ></textarea>
        <button class="human-btn" @click="sendQuery('我要转人工')" :disabled="isLoading" title="转人工客服">转人工</button>
        <button class="send-btn" :disabled="!inputQuery.trim() || isLoading" @click="sendQuery(inputQuery)">
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'

// ---- 状态 ----
const inputQuery = ref('')
const isLoading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)

const SESSION_ID = 'service_session'
const API_BASE = '' // 相对路径：本地 vite proxy / 容器 nginx 同源代理

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<Message[]>([])

const quickQuestions = [
  'iPhone 15 Pro 内存多大？',
  '预算 5000 买什么手机？',
  '现在有什么优惠券？',
  '帮我查一下最近的订单',
  '七天无理由退货有什么条件？',
]

// ---- 鉴权 ----
const TOKEN_KEY = 'shop_service_token'
const USER_KEY = 'shop_service_user'
const currentUser = ref('user_1001')
let token = ''

async function ensureToken(userId: string): Promise<string> {
  const r = await fetch(`${API_BASE}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  })
  if (!r.ok) throw new Error(`auth failed: ${r.status}`)
  const d = await r.json()
  localStorage.setItem(TOKEN_KEY, d.token)
  localStorage.setItem(USER_KEY, userId)
  return d.token
}

async function loadOrCreateToken(): Promise<string> {
  const savedUser = localStorage.getItem(USER_KEY) || 'user_1001'
  currentUser.value = savedUser
  const savedToken = localStorage.getItem(TOKEN_KEY)
  if (savedToken) return savedToken
  return ensureToken(savedUser)
}

async function switchUser() {
  const uid = window.prompt('输入要切换的 user_id（如 user_1002）', currentUser.value)
  if (!uid || !uid.trim()) return
  currentUser.value = uid.trim()
  localStorage.setItem(USER_KEY, currentUser.value)
  localStorage.removeItem(TOKEN_KEY)
  token = await ensureToken(currentUser.value)
  messages.value = []
  saveState()
}

async function endSession() {
  try {
    await fetch(`${API_BASE}/api/session/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ session_id: SESSION_ID }),
    })
    messages.value.push({ role: 'assistant', content: '本轮会话已结束，您的偏好已被记录。欢迎继续咨询 😊' })
    saveState()
    scrollToBottom()
  } catch (e) {
    console.error('结束会话失败', e)
  }
}

function clearChat() {
  messages.value = []
  saveState()
}

// ---- 工单号提取 ----
function ticketNoOf(content: string): string | null {
  const m = content.match(/工单号[：:]\s*([A-Z0-9-]+)/)
  return m?.[1] ?? null
}

// ---- 持久化 ----
const STORAGE_KEY = 'shop_service_chat'
const saveState = () => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.value)) } catch (e) { /* 忽略 */ }
}
const loadState = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const list = JSON.parse(saved)
      if (Array.isArray(list)) messages.value = list
    }
  } catch (e) { /* 忽略 */ }
}

onMounted(async () => {
  loadState()  // 先读本地兜底
  try {
    token = await loadOrCreateToken()
    // 从后端恢复会话历史（跨设备 / 刷新后仍能接上）
    const r = await fetch(`${API_BASE}/api/session/history?session_id=${SESSION_ID}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (r.ok) {
      const d = await r.json()
      if (d.messages && d.messages.length > 0) {
        messages.value = d.messages.map((m: { role: 'user' | 'assistant'; content: string }) => ({ role: m.role, content: m.content }))
        saveState()
        scrollToBottom()
      }
    }
  } catch (e) { console.error('登录失败，请确认后端已启动', e) }
})

// ---- Markdown ----
const renderMarkdown = (text: string): string => {
  const html = marked.parse(text, { gfm: true, breaks: true })
  return typeof html === 'string' ? html : ''
}

const scrollToBottom = async () => {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

const handleEnter = (e: KeyboardEvent) => {
  if (e.shiftKey) return
  if (inputQuery.value.trim() && !isLoading.value) sendQuery(inputQuery.value)
}

const sendQuery = async (query: string) => {
  if (!query.trim() || isLoading.value) return
  if (!token) {
    messages.value.push({ role: 'assistant', content: '❌ 尚未登录，请刷新页面重试。' })
    return
  }
  const text = query.trim()
  inputQuery.value = ''
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()
  isLoading.value = true

  const assistantMessage: Message = { role: 'assistant', content: '' }
  messages.value.push(assistantMessage)
  const currentMsgIndex = messages.value.length - 1

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ query: text, session_id: SESSION_ID }),
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

    const reader = response.body?.getReader()
    const decoder = new TextDecoder('utf-8')
    if (reader) {
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (dataStr === '[DONE]' || !dataStr) continue
          try {
            const data = JSON.parse(dataStr)
            if (data.status === 'thinking') continue
            if (data.content && messages.value[currentMsgIndex]) {
              isLoading.value = false
              messages.value[currentMsgIndex].content += data.content
              scrollToBottom()
            }
            if (data.done) isLoading.value = false
          } catch (e) { /* 忽略单条解析错误 */ }
        }
      }
    }
  } catch (error) {
    console.error('API Error:', error)
    if (messages.value[currentMsgIndex]) {
      messages.value[currentMsgIndex].content = '❌ 请求失败，请稍后重试。'
    }
  } finally {
    isLoading.value = false
    scrollToBottom()
    saveState()
  }
}
</script>

<style scoped>
/* ===== 设计变量 ===== */
.chat-container {
  --primary: #4f46e5;
  --primary-dark: #4338ca;
  --bg: #f4f6fb;
  --user-bubble: linear-gradient(135deg, #4f46e5, #6366f1);
  --assistant-bubble: #ffffff;
  --text: #1f2430;
  --muted: #8a919e;
  --border: #e7eaf3;
  height: 100vh;
  width: 100vw;
  background: var(--bg);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  box-sizing: border-box;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.chat-window {
  width: 100%;
  max-width: 760px;
  height: 100%;
  max-height: 920px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 12px 40px rgba(30, 41, 59, 0.10);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== 头部 ===== */
.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  background: #fff;
  flex-shrink: 0;
}
.service-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  font-weight: 700;
  flex-shrink: 0;
}
.service-info { flex: 1; min-width: 0; }
.service-name { font-size: 16px; font-weight: 650; color: var(--text); }
.service-status {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
}
.online-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.18);
  display: inline-block;
}
.header-actions { display: flex; gap: 8px; }
.ghost-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: #4b5563;
  border-radius: 9px;
  padding: 6px 11px;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
.ghost-btn:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.ghost-btn:disabled { opacity: .5; cursor: not-allowed; }

/* ===== 消息区 ===== */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  background: #fafbfe;
  scroll-behavior: smooth;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 40px;
  gap: 18px;
}
.welcome-card {
  text-align: center;
  max-width: 80%;
}
.welcome-title { font-size: 18px; font-weight: 650; color: var(--text); }
.welcome-sub { font-size: 14px; color: var(--muted); margin-top: 8px; line-height: 1.6; }
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 92%;
}
.quick-item {
  background: #fff;
  border: 1px solid var(--border);
  color: #4b5563;
  border-radius: 999px;
  padding: 8px 15px;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
}
.quick-item:hover { border-color: var(--primary); color: var(--primary); background: #f5f5ff; }

.message-row { display: flex; gap: 10px; margin-bottom: 18px; align-items: flex-start; }
.message-row.user { flex-direction: row-reverse; }
.msg-avatar {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff; flex-shrink: 0;
}
.message-row.user .msg-avatar { background: linear-gradient(135deg, #4f46e5, #6366f1); }
.message-row.assistant .msg-avatar { background: linear-gradient(135deg, #7c3aed, #a855f7); }
.msg-body { max-width: 78%; }
.message-bubble {
  padding: 11px 15px;
  border-radius: 4px 14px 14px 14px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text);
  background: var(--assistant-bubble);
  border: 1px solid var(--border);
  word-break: break-word;
}
.message-row.user .message-bubble {
  background: var(--user-bubble);
  color: #fff;
  border: none;
  border-radius: 14px 4px 14px 14px;
}
.ticket-chip {
  margin-top: 8px;
  font-size: 12.5px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 6px 10px;
  display: inline-block;
}
.ticket-chip code { background: #fef3c7; padding: 1px 5px; border-radius: 4px; font-weight: 600; }

/* Markdown 内容样式 */
.message-bubble :deep(p) { margin: 0 0 8px 0; }
.message-bubble :deep(p:last-child) { margin-bottom: 0; }
.message-bubble :deep(h1), .message-bubble :deep(h2), .message-bubble :deep(h3) { margin: 10px 0 6px; font-weight: 650; }
.message-bubble :deep(ul), .message-bubble :deep(ol) { margin: 6px 0; padding-left: 20px; }
.message-bubble :deep(table) { border-collapse: collapse; margin: 8px 0; font-size: 13px; width: 100%; }
.message-bubble :deep(th), .message-bubble :deep(td) { border: 1px solid #e5e7eb; padding: 5px 9px; text-align: left; }
.message-bubble :deep(th) { background: #f3f4f6; }
.message-bubble :deep(pre) {
  background: #0f172a; color: #e2e8f0; padding: 12px 14px; border-radius: 10px;
  overflow-x: auto; font-size: 13px; line-height: 1.5; margin: 8px 0;
}
.message-bubble :deep(code) { background: #eef2ff; color: #4338ca; padding: 1px 5px; border-radius: 4px; font-size: 13px; }
.message-bubble :deep(pre code) { background: none; color: inherit; padding: 0; }
.message-bubble :deep(a) { color: #4f46e5; }
.message-row.user .message-bubble :deep(code) { background: rgba(255,255,255,.2); color: #fff; }

/* 正在输入动画 */
.message-bubble.typing { display: flex; gap: 5px; align-items: center; padding: 14px 16px; }
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #c7cbe0;
  animation: blink 1.4s infinite both;
}
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: .25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); }
}

/* ===== 输入区 ===== */
.input-area {
  display: flex;
  gap: 9px;
  padding: 14px 18px;
  border-top: 1px solid var(--border);
  background: #fff;
  align-items: flex-end;
  flex-shrink: 0;
}
.input-area textarea {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 11px 14px;
  font-size: 14px;
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
  max-height: 120px;
  transition: border-color .15s;
}
.input-area textarea:focus { border-color: var(--primary); }
.human-btn {
  background: #fff;
  color: #b45309;
  border: 1px solid #fbbf24;
  border-radius: 11px;
  padding: 11px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
.human-btn:hover:not(:disabled) { background: #fffbeb; }
.human-btn:disabled { opacity: .5; cursor: not-allowed; }
.send-btn {
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 11px;
  padding: 11px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
}
.send-btn:hover:not(:disabled) { background: var(--primary-dark); }
.send-btn:disabled { background: #c7cbe0; cursor: not-allowed; }
</style>
