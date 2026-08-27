import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getAgentConfig, checkAgentHealth,
  agentChatStream, agentChat,
  getAgentSessions, getAgentSession, clearAgentSession,
} from '../api'
import { marked } from 'marked'
import { sanitizeHtml } from '../utils/safeHtml'

// marked 配置：中断单行换行（聊天场景更自然）
marked.setOptions({ breaks: true, gfm: true })

/** 渲染 assistant 消息的 markdown：先 parse 再 sanitize，防注入 */
export function renderChatMarkdown(text) {
  if (!text) return ''
  return sanitizeHtml(marked.parse(text))
}

export const useAgentStore = defineStore('agent', () => {
  // ───────── 对话状态 ─────────
  const sessionId = ref('default')
  const messages = ref([])      // [{ role, content, streaming? }]
  const chatLoading = ref(false)
  const chatBackend = ref('')
  const sessionsList = ref([])

  // ───────── 配置状态 ─────────
  const config = ref({ apiBase: '', apiKeyMasked: '', model: '', hasKey: false })
  const healthStatus = ref(null)
  const healthLoading = ref(false)

  // ───────── Tab 结果状态 ─────────
  const summarizeResult = ref(null)
  const summarizeLoading = ref(false)
  const organizeResult = ref(null)
  const organizeLoading = ref(false)
  const pathResult = ref(null)
  const pathLoading = ref(false)
  const algoResult = ref(null)
  const algoLoading = ref(false)

  const canSend = computed(() => !chatLoading.value)

  // ───────── 对话操作 ─────────

  async function loadHistory(sid = sessionId.value) {
    sessionId.value = sid
    messages.value = []
    chatBackend.value = ''
    try {
      const r = await getAgentSession(sid)
      messages.value = (r.messages || []).map(m => ({
        id: m.id, role: m.role, content: m.content,
      }))
    } catch { /* 新会话无历史 */ }
    loadSessions()
  }

  async function loadSessions() {
    try {
      const s = await getAgentSessions()
      sessionsList.value = s.sessions || []
    } catch { /* ignore */ }
  }

  async function sendChatStream(userMessage) {
    if (chatLoading.value) return
    chatLoading.value = true

    // 乐观追加 user 消息 + 占位 assistant 消息
    messages.value.push({ role: 'user', content: userMessage })
    messages.value.push({ role: 'assistant', content: '', streaming: true })
    // 取响应式代理引用（直接改 raw 对象不触发视图更新）
    const assistantMsg = messages.value[messages.value.length - 1]

    await agentChatStream(
      sessionId.value,
      userMessage,
      (chunk) => { assistantMsg.content += chunk },
      ({ error, backend }) => {
        if (backend) chatBackend.value = backend
        if (error) {
          assistantMsg.content += `\n\n⚠️ ${error}`
        }
        delete assistantMsg.streaming
      },
    )
    chatLoading.value = false
    loadSessions()
  }

  /** 非流式兜底（SSE 不可用时） */
  async function sendChat(userMessage) {
    if (chatLoading.value) return
    chatLoading.value = true
    messages.value.push({ role: 'user', content: userMessage })
    try {
      const r = await agentChat(sessionId.value, userMessage)
      if (r.error) throw new Error(r.error)
      messages.value.push({ role: 'assistant', content: r.reply })
      if (r.backend) chatBackend.value = r.backend
    } catch (e) {
      messages.value.push({ role: 'assistant', content: `⚠️ ${e.message}` })
    } finally {
      chatLoading.value = false
    }
  }

  async function clearChat() {
    try {
      await clearAgentSession(sessionId.value)
    } catch { /* ignore */ }
    messages.value = []
    loadSessions()
  }

  // ───────── 配置操作 ─────────

  async function loadConfig() {
    try {
      config.value = await getAgentConfig()
    } catch (e) {
      config.value = { apiBase: '', apiKeyMasked: '', model: '', hasKey: false, error: e.message }
    }
  }

  async function checkHealth() {
    healthLoading.value = true
    try {
      healthStatus.value = await checkAgentHealth()
    } catch (e) {
      healthStatus.value = { ok: false, error: e.message }
    } finally {
      healthLoading.value = false
    }
  }

  return {
    // 对话
    sessionId, messages, chatLoading, chatBackend, sessionsList,
    canSend, loadHistory, loadSessions, sendChatStream, sendChat, clearChat,
    // 配置
    config, healthStatus, healthLoading, loadConfig, checkHealth,
    // Tab 结果
    summarizeResult, summarizeLoading,
    organizeResult, organizeLoading,
    pathResult, pathLoading,
    algoResult, algoLoading,
  }
})
