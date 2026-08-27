<script setup>
/**
 * AI Agent 面板
 *
 * 五大功能 Tab：
 *   1. 对话     — 流式输出（SSE）+ markdown 渲染 + SQLite 持久记忆
 *   2. 整理笔记  — 单篇摘要/知识点/复习题；批量聚类与顺序
 *   3. 学习路径  — 基于历史+目标的个性化路径推荐
 *   4. 算法优化  — 分析学习模式，给出推荐算法调参建议
 *   5. 配置     — 双后端配置（Hermes 优先 / pcl 兜底），Key 脱敏显示
 *
 * 状态管理：对话/配置/各 Tab 结果在 stores/agent.js（Pinia），
 * 本组件只保留 UI 交互状态（tab、输入框、编辑草稿）。
 */
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNotesStore } from '../stores/notes'
import { useAgentStore, renderChatMarkdown } from '../stores/agent'
import AppHeader from '../components/AppHeader.vue'
import AppIcon from '../components/AppIcon.vue'
import {
  setAgentConfig,
  agentSummarize, agentOrganize, agentRecommendPath, agentOptimizeAlgorithm,
} from '../api'

const router = useRouter()
const notes = useNotesStore()
const agent = useAgentStore()

// ───────── UI 状态 ─────────
const tab = ref('chat') // 'chat' | 'organize' | 'path' | 'algo' | 'config'
const chatInput = ref('')
const chatWindowRef = ref(null)

// 配置编辑（草稿，保存前不影响运行配置）
const cfgEditing = ref(false)
const cfgDraft = ref({ apiBase: '', apiKey: '', model: '', hermesUrl: '', hermesKey: '', backend: 'auto' })
const cfgSaving = ref(false)
const cfgMsg = ref('')

// 各 Tab 的输入
const summarizeName = ref('')
const organizeCat = ref('')
const goal = ref('')

const noteNames = computed(() =>
  notes.items.map(n => ({ id: n.id, name: n.name.replace(/\.md$/, ''), cat: n.cat }))
)
const catOptions = computed(() => {
  const s = new Set(notes.items.map(n => n.cat))
  return [...s]
})

onMounted(async () => {
  notes.load()
  await agent.loadConfig()
  cfgDraft.value = {
    apiBase: agent.config.apiBase, apiKey: '', model: agent.config.model,
    hermesUrl: agent.config.hermesUrl || '', hermesKey: '',
    backend: agent.config.backend || 'auto',
  }
  await agent.loadHistory()
})

// ───────── 对话 ─────────

async function sendChat() {
  const msg = chatInput.value.trim()
  if (!msg || agent.chatLoading) return
  chatInput.value = ''
  await agent.sendChatStream(msg)
}

function onChatEnter(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendChat()
  }
}

/** 消息变化时自动滚动到底部（流式输出时持续跟随） */
async function scrollToBottom() {
  await nextTick()
  const el = chatWindowRef.value
  if (el) el.scrollTop = el.scrollHeight
}

// 监听流式输出：每条消息内容变化就滚动
watch(() => agent.messages.map(m => m.content).join('\x00'), scrollToBottom)

// ───────── 配置 ─────────

async function saveConfig() {
  cfgSaving.value = true
  cfgMsg.value = ''
  try {
    await setAgentConfig({
      apiBase: cfgDraft.value.apiBase,
      apiKey: cfgDraft.value.apiKey || undefined,
      model: cfgDraft.value.model,
      hermesUrl: cfgDraft.value.hermesUrl,
      hermesKey: cfgDraft.value.hermesKey || undefined,
      backend: cfgDraft.value.backend,
    })
    await agent.loadConfig()
    cfgEditing.value = false
    cfgMsg.value = '已保存'
  } catch (e) {
    cfgMsg.value = '保存失败：' + e.message
  } finally {
    cfgSaving.value = false
    setTimeout(() => { cfgMsg.value = '' }, 2500)
  }
}

// ───────── 各 Tab 功能 ─────────

async function runSummarize() {
  if (!summarizeName.value) return
  agent.summarizeLoading = true
  agent.summarizeResult = null
  try {
    agent.summarizeResult = await agentSummarize(summarizeName.value)
  } catch (e) {
    agent.summarizeResult = { error: e.message }
  } finally {
    agent.summarizeLoading = false
  }
}

async function runOrganize() {
  agent.organizeLoading = true
  agent.organizeResult = null
  try {
    agent.organizeResult = await agentOrganize(organizeCat.value)
  } catch (e) {
    agent.organizeResult = { error: e.message }
  } finally {
    agent.organizeLoading = false
  }
}

async function runRecommendPath() {
  agent.pathLoading = true
  agent.pathResult = null
  try {
    agent.pathResult = await agentRecommendPath(goal.value)
  } catch (e) {
    agent.pathResult = { error: e.message }
  } finally {
    agent.pathLoading = false
  }
}

async function runOptimizeAlgo() {
  agent.algoLoading = true
  agent.algoResult = null
  try {
    agent.algoResult = await agentOptimizeAlgorithm()
  } catch (e) {
    agent.algoResult = { error: e.message }
  } finally {
    agent.algoLoading = false
  }
}

function findNoteName(id) {
  const n = notes.items.find(x => x.id === id)
  return n ? n.name.replace(/\.md$/, '') : id
}

function openNote(id) {
  const n = notes.items.find(x => x.id === id)
  if (!n) return
  router.push('/')
  setTimeout(() => {
    window.dispatchEvent(new CustomEvent('note-navigation-request', { detail: { id, cat: n.cat } }))
  }, 200)
}

const DIFF_COLORS = { '入门': '#10b981', '进阶': '#f59e0b', '专家': '#ef4444' }

// Tab 定义（图标 + 标签）
const TABS = [
  { k: 'chat', label: '对话', icon: 'message' },
  { k: 'organize', label: '整理笔记', icon: 'list' },
  { k: 'path', label: '学习路径', icon: 'route' },
  { k: 'algo', label: '算法优化', icon: 'zap' },
  { k: 'config', label: '配置', icon: 'settings' },
]
</script>

<template>
  <div class="agent-page">
    <!-- 共享顶栏 -->
    <AppHeader title="AI 学习助手">
      <span class="badge-pill" v-if="agent.config.model">
        <AppIcon name="zap" :size="11" /> {{ agent.config.model }}
      </span>
      <span class="badge-pill" :class="(agent.config.hasKey || agent.config.hasHermesKey) ? 'ok' : ''">
        <AppIcon name="key" :size="11" />
        {{ agent.config.hasKey || agent.config.hasHermesKey ? 'Key 已配置' : '未配置 Key' }}
      </span>
    </AppHeader>

    <div class="agent-body">
      <!-- Tab 条 -->
      <nav class="agent-tabs">
        <button
          v-for="t in TABS"
          :key="t.k"
          :class="{ active: tab === t.k }"
          @click="tab = t.k"
        >
          <AppIcon :name="t.icon" :size="14" />
          {{ t.label }}
        </button>
      </nav>

      <!-- 页面主体：撑满剩余视口 -->
      <div class="agent-content">
      <!-- ───── 对话（SQLite 持久记忆 + 流式输出）───── -->
      <section v-if="tab === 'chat'" class="agent-section chat-section">
        <div class="chat-head">
          <div class="chat-head-left">
            <h2>AI 学习助手对话</h2>
            <span class="badge-pill accent" v-if="agent.chatBackend">
              <AppIcon name="zap" :size="11" /> {{ agent.chatBackend }}
            </span>
          </div>
          <div class="chat-head-right">
            <input v-model="agent.sessionId" class="input session-input" placeholder="会话 ID"
                   @change="agent.loadHistory()" />
            <button class="btn-ghost inline-flex" @click="agent.clearChat()">
              <AppIcon name="trash" :size="13" /> 清空记忆
            </button>
          </div>
        </div>
        <div class="chat-window" ref="chatWindowRef">
          <div v-if="!agent.messages.length" class="chat-empty">
            <AppIcon name="message" :size="28" stroke-width="1.5" class="chat-empty-icon" />
            <p class="chat-empty-title">开始与 AI 助手对话</p>
            <p class="chat-empty-hint">
              帮我整理最近学的内容 · 我下一步应该学什么 · Docker 网络有哪些知识点
            </p>
            <span class="chat-tip">对话记忆持久化保存（SQLite），重启后端不会丢失</span>
          </div>
          <div v-for="(m, i) in agent.messages" :key="i" class="chat-msg msg-in" :class="m.role">
            <div class="chat-avatar" :class="m.role">
              <AppIcon :name="m.role === 'user' ? 'user' : 'bot'" :size="15" />
            </div>
            <!-- assistant 消息用 markdown 渲染；user 消息保持纯文本 -->
            <div v-if="m.role === 'assistant'" class="chat-bubble md">
              <div class="md-body" v-html="renderChatMarkdown(m.content)"></div>
              <span v-if="m.streaming && !m.content" class="typing-dots"><span></span><span></span><span></span></span>
              <span v-if="m.streaming && m.content" class="stream-cursor"></span>
            </div>
            <div v-else class="chat-bubble">{{ m.content }}</div>
          </div>
        </div>
        <div class="chat-input-row">
          <textarea
            v-model="chatInput"
            class="chat-input"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            rows="2"
            @keydown="onChatEnter"
          ></textarea>
          <button class="btn-primary send-btn" :disabled="!chatInput.trim() || agent.chatLoading" @click="sendChat">
            <AppIcon name="send" :size="14" />
            {{ agent.chatLoading ? '生成中…' : '发送' }}
          </button>
        </div>
      </section>

      <!-- ───── 整理笔记 ───── -->
      <section v-if="tab === 'organize'" class="agent-section">
        <div class="agent-grid">
          <!-- 单篇整理 -->
          <div class="card">
            <div class="card-head">
              <h2>单篇笔记整理</h2>
              <p class="card-desc">AI 生成摘要、知识点、复习题与难度评估</p>
            </div>
            <div class="card-form">
              <select v-model="summarizeName" class="input">
                <option value="">选择笔记…</option>
                <option v-for="n in noteNames" :key="n.id" :value="n.name">
                  [{{ n.cat }}] {{ n.name }}
                </option>
              </select>
              <button class="btn-primary" :disabled="!summarizeName || agent.summarizeLoading" @click="runSummarize">
                {{ agent.summarizeLoading ? '整理中…' : '开始整理' }}
              </button>
            </div>
            <div v-if="agent.summarizeLoading" class="loading">⏳ AI 正在阅读笔记…</div>
            <div v-if="agent.summarizeResult && !agent.summarizeLoading" class="result">
              <div v-if="agent.summarizeResult.error" class="error-box">{{ agent.summarizeResult.error }}</div>
              <template v-else>
                <div class="result-block">
                  <div class="block-label">摘要</div>
                  <p class="block-text">{{ agent.summarizeResult.summary }}</p>
                </div>
                <div class="result-block" v-if="agent.summarizeResult.key_points?.length">
                  <div class="block-label">核心知识点</div>
                  <ul class="block-list">
                    <li v-for="(p, i) in agent.summarizeResult.key_points" :key="i">{{ p }}</li>
                  </ul>
                </div>
                <div class="result-block" v-if="agent.summarizeResult.review_questions?.length">
                  <div class="block-label">复习自测题</div>
                  <ul class="block-list">
                    <li v-for="(q, i) in agent.summarizeResult.review_questions" :key="i">{{ q }}</li>
                  </ul>
                </div>
                <div class="result-meta">
                  <span class="badge" :style="{ background: DIFF_COLORS[agent.summarizeResult.difficulty] || '#64748b' }">
                    {{ agent.summarizeResult.difficulty || '未知' }}
                  </span>
                  <span class="badge-line" v-if="agent.summarizeResult.prerequisites?.length">
                    建议先学：{{ agent.summarizeResult.prerequisites.join('、') }}
                  </span>
                </div>
              </template>
            </div>
          </div>

          <!-- 批量聚类 -->
          <div class="card">
            <div class="card-head">
              <h2>批量聚类整理</h2>
              <p class="card-desc">按主题分组，给出建议学习顺序</p>
            </div>
            <div class="card-form">
              <select v-model="organizeCat" class="input">
                <option value="">全部分类</option>
                <option v-for="c in catOptions" :key="c" :value="c">{{ c }}</option>
              </select>
              <button class="btn-primary" :disabled="agent.organizeLoading" @click="runOrganize">
                {{ agent.organizeLoading ? '聚类中…' : '开始整理' }}
              </button>
            </div>
            <div v-if="agent.organizeLoading" class="loading">⏳ AI 正在分析笔记关系…</div>
            <div v-if="agent.organizeResult && !agent.organizeLoading" class="result">
              <div v-if="agent.organizeResult.error" class="error-box">{{ agent.organizeResult.error }}</div>
              <template v-else>
                <div v-if="agent.organizeResult.clusters?.length" class="clusters">
                  <div v-for="(c, i) in agent.organizeResult.clusters" :key="i" class="cluster">
                    <div class="cluster-head">
                      <span class="cluster-no">{{ i + 1 }}</span>
                      <span class="cluster-topic">{{ c.topic }}</span>
                    </div>
                    <p class="cluster-reason">{{ c.reason }}</p>
                    <div class="cluster-notes">
                      <button v-for="nid in c.note_ids" :key="nid" class="chip" @click="openNote(nid)">
                        {{ findNoteName(nid) }}
                      </button>
                    </div>
                  </div>
                </div>
                <div v-if="agent.organizeResult.tips?.length" class="result-block">
                  <div class="block-label">学习建议</div>
                  <ul class="block-list">
                    <li v-for="(t, i) in agent.organizeResult.tips" :key="i">{{ t }}</li>
                  </ul>
                </div>
              </template>
            </div>
          </div>
        </div>
      </section>

      <!-- ───── 学习路径 ───── -->
      <section v-if="tab === 'path'" class="agent-section">
        <div class="card">
          <div class="card-head">
            <h2>个性化学习路径推荐</h2>
            <p class="card-desc">基于你的学习历史与目标，AI 规划循序渐进的学习路线</p>
          </div>
          <div class="card-form">
            <input v-model="goal" class="input flex-1" placeholder="学习目标（可选，如：掌握 K8s 生产部署）" />
            <button class="btn-primary" :disabled="agent.pathLoading" @click="runRecommendPath">
              {{ agent.pathLoading ? '规划中…' : '推荐路径' }}
            </button>
          </div>
          <div v-if="agent.pathLoading" class="loading">⏳ AI 正在为你规划学习路径…</div>
          <div v-if="agent.pathResult && !agent.pathLoading" class="result">
            <div v-if="agent.pathResult.error" class="error-box">{{ agent.pathResult.error }}</div>
            <template v-else>
              <div v-if="agent.pathResult.path?.length" class="path-steps">
                <div v-for="(s, i) in agent.pathResult.path" :key="i" class="path-step">
                  <div class="step-no">{{ s.step }}</div>
                  <div class="step-body">
                    <button class="step-title" @click="openNote(s.note_id)">
                      {{ s.note_name }}
                      <span class="step-hours" v-if="s.estimated_hours">≈ {{ s.estimated_hours }}h</span>
                    </button>
                    <p class="step-reason">{{ s.reason }}</p>
                  </div>
                </div>
              </div>
              <div v-if="agent.pathResult.milestones?.length" class="result-block">
                <div class="block-label">阶段性里程碑</div>
                <ul class="block-list">
                  <li v-for="(m, i) in agent.pathResult.milestones" :key="i">{{ m }}</li>
                </ul>
              </div>
              <div v-if="agent.pathResult.gaps?.length" class="result-block">
                <div class="block-label">知识缺口</div>
                <ul class="block-list">
                  <li v-for="(g, i) in agent.pathResult.gaps" :key="i">{{ g }}</li>
                </ul>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- ───── 算法优化 ───── -->
      <section v-if="tab === 'algo'" class="agent-section">
        <div class="card">
          <div class="card-head">
            <h2>学习算法优化</h2>
            <p class="card-desc">AI 分析你的学习模式，给出间隔重复与推荐算法的调参建议</p>
          </div>
          <div class="card-form">
            <button class="btn-primary" :disabled="agent.algoLoading" @click="runOptimizeAlgo">
              {{ agent.algoLoading ? '分析中…' : '开始分析' }}
            </button>
          </div>
          <div v-if="agent.algoLoading" class="loading">⏳ AI 正在分析你的学习模式…</div>
          <div v-if="agent.algoResult && !agent.algoLoading" class="result">
            <div v-if="agent.algoResult.error" class="error-box">{{ agent.algoResult.error }}</div>
            <template v-else>
              <div class="result-block" v-if="agent.algoResult.analysis">
                <div class="block-label">学习模式分析</div>
                <p class="block-text">{{ agent.algoResult.analysis }}</p>
              </div>
              <div v-if="agent.algoResult.recommendations?.length" class="opt-table">
                <table>
                  <thead>
                    <tr><th>参数</th><th>当前</th><th>建议</th><th>理由</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(r, i) in agent.algoResult.recommendations" :key="i">
                      <td><code>{{ r.param }}</code></td>
                      <td>{{ r.current }}</td>
                      <td class="suggested">{{ r.suggested }}</td>
                      <td>{{ r.reason }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="result-block" v-if="agent.algoResult.strategy">
                <div class="block-label">个性化学习策略</div>
                <p class="block-text">{{ agent.algoResult.strategy }}</p>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- ───── 配置 ───── -->
      <section v-if="tab === 'config'" class="agent-section">
        <div class="card">
          <div class="card-head">
            <h2>Agent 配置</h2>
            <p class="card-desc">双后端：Hermes Agent 优先（共享记忆），pcl GLM API 兜底。Key 存于本地 user_data，脱敏显示</p>
          </div>
          <div class="config-row">
            <div class="config-label">后端模式</div>
            <div class="config-value">{{ agent.config.backend || 'auto' }}</div>
          </div>
          <div class="config-row">
            <div class="config-label">Hermes URL</div>
            <div class="config-value">{{ agent.config.hermesUrl || '—' }}</div>
          </div>
          <div class="config-row">
            <div class="config-label">Hermes Key</div>
            <div class="config-value">{{ agent.config.hermesKeyMasked || '—' }} <span class="badge-pill" :class="agent.config.hasHermesKey ? 'ok' : 'warn'">{{ agent.config.hasHermesKey ? '已配置' : '未配置' }}</span></div>
          </div>
          <div class="config-row">
            <div class="config-label">pcl API 地址</div>
            <div class="config-value">{{ agent.config.apiBase || '—' }}</div>
          </div>
          <div class="config-row">
            <div class="config-label">模型</div>
            <div class="config-value">{{ agent.config.model || '—' }}</div>
          </div>
          <div class="config-row">
            <div class="config-label">pcl API Key</div>
            <div class="config-value">{{ agent.config.apiKeyMasked || '—' }} <span class="badge-pill" :class="agent.config.hasKey ? 'ok' : 'warn'">{{ agent.config.hasKey ? '已配置' : '未配置' }}</span></div>
          </div>

          <div class="config-actions">
            <button class="btn-primary" @click="agent.checkHealth()" :disabled="agent.healthLoading">
              {{ agent.healthLoading ? '检测中…' : '检测连通性' }}
            </button>
            <button class="btn-ghost" @click="cfgEditing = !cfgEditing">
              {{ cfgEditing ? '取消' : '修改配置' }}
            </button>
          </div>

          <div v-if="agent.healthStatus" class="health-box" :class="agent.healthStatus.ok ? 'ok' : 'fail'">
            <strong>{{ agent.healthStatus.ok ? '✅ 连通正常' : '❌ 连通失败' }}</strong>
            <span v-if="agent.healthStatus.ok && agent.healthStatus.reply"> · 响应：{{ agent.healthStatus.reply }}</span>
            <span v-if="agent.healthStatus.ok && agent.healthStatus.backend"> · 后端：{{ agent.healthStatus.backend }}{{ agent.healthStatus.fallback ? '（兜底）' : '' }}</span>
            <span v-if="!agent.healthStatus.ok && agent.healthStatus.error"> · {{ agent.healthStatus.error }}</span>
          </div>

          <div v-if="cfgEditing" class="cfg-edit">
            <div class="config-row">
              <div class="config-label">后端模式</div>
              <select v-model="cfgDraft.backend" class="input">
                <option value="auto">auto（Hermes 优先，失败切 pcl）</option>
                <option value="hermes">hermes（仅 Hermes）</option>
                <option value="pcl">pcl（仅 pcl GLM）</option>
              </select>
            </div>
            <div class="config-row">
              <div class="config-label">Hermes URL</div>
              <input v-model="cfgDraft.hermesUrl" class="input" placeholder="http://172.22.40.153:8642/v1" />
            </div>
            <div class="config-row">
              <div class="config-label">新 Hermes Key</div>
              <input v-model="cfgDraft.hermesKey" class="input" type="password" placeholder="留空保留旧值" />
            </div>
            <div class="config-row">
              <div class="config-label">pcl API 地址</div>
              <input v-model="cfgDraft.apiBase" class="input" placeholder="https://llmapi.pcl.ac.cn/v1" />
            </div>
            <div class="config-row">
              <div class="config-label">模型 ID</div>
              <input v-model="cfgDraft.model" class="input" placeholder="GLM-5.2" />
            </div>
            <div class="config-row">
              <div class="config-label">新 pcl API Key</div>
              <input v-model="cfgDraft.apiKey" class="input" type="password" placeholder="留空保留旧值" />
            </div>
            <button class="btn-primary" :disabled="cfgSaving" @click="saveConfig">
              {{ cfgSaving ? '保存中…' : '保存' }}
            </button>
            <span v-if="cfgMsg" class="cfg-msg">{{ cfgMsg }}</span>
          </div>
        </div>
      </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
}

.agent-body {
  flex: 1;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 1.5rem 2rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.agent-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: 1px solid var(--line);
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  transition: border-color 0.15s, color 0.15s;
}
.btn-ghost:hover { border-color: var(--accent); color: var(--accent); }

/* ───── Tab 条 ───── */
.agent-tabs {
  display: flex;
  gap: 4px;
  padding: 14px 0;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line);
}
.agent-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: transparent;
  border: 1px solid transparent;
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--muted);
  font-size: 13.5px;
  font-weight: 600;
  font-family: inherit;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.agent-tabs button:hover { background: var(--hover); color: var(--text); }
.agent-tabs button.active {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 22%, transparent);
}

.agent-section { display: flex; flex-direction: column; gap: 12px; padding-top: 14px; }
.agent-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
@media (max-width: 800px) { .agent-grid { grid-template-columns: 1fr; } }

/* 可滚动的内容区（非聊天 Tab：正常纵向滚动） */
.agent-content > section:not(.chat-section) {
  overflow-y: auto;
}

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px;
}
.card-head h2 { font-size: 15px; margin: 0 0 4px; font-weight: 700; }
.card-desc { font-size: 12.5px; color: var(--muted); margin: 0 0 14px; }
.card-form { display: flex; gap: 8px; margin-bottom: 14px; }
.input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--line);
  padding: 8px 10px;
  border-radius: 8px;
  color: var(--text);
  font-size: 13.5px;
  min-width: 0;
  font-family: inherit;
}
.input:focus { outline: none; border-color: var(--accent); }
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13.5px;
  font-weight: 600;
  white-space: nowrap;
  font-family: inherit;
  transition: opacity 0.15s;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary:not(:disabled):hover { opacity: 0.9; }

.loading {
  padding: 24px;
  text-align: center;
  color: var(--muted);
  font-size: 13.5px;
}
.result { margin-top: 8px; display: flex; flex-direction: column; gap: 14px; }
.error-box {
  padding: 12px 14px;
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent);
  border-radius: 8px;
  color: var(--danger);
  font-size: 13px;
}
.result-block { }
.block-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.block-text { font-size: 13.5px; line-height: 1.65; margin: 0; color: var(--text); }
.block-list { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.75; }
.block-list li { margin-bottom: 3px; }
.result-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.badge {
  padding: 3px 10px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.badge-line { font-size: 12px; color: var(--muted); }

.clusters { display: flex; flex-direction: column; gap: 10px; }
.cluster {
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.cluster-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cluster-no {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11.5px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.cluster-topic { font-weight: 700; font-size: 14px; }
.cluster-reason { font-size: 12.5px; color: var(--muted); margin: 0 0 8px; }
.cluster-notes { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  background: var(--card);
  border: 1px solid var(--line);
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  font-family: inherit;
  transition: border-color 0.15s, color 0.15s;
}
.chip:hover { border-color: var(--accent); color: var(--accent); }

.path-steps { display: flex; flex-direction: column; gap: 10px; }
.path-step {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 10px;
}
.step-no {
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 50%;
  background: var(--accent-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12.5px;
}
.step-body { flex: 1; }
.step-title {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  font-family: inherit;
}
.step-title:hover { color: var(--accent); }
.step-hours {
  margin-left: 8px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--muted);
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--card);
}
.step-reason { font-size: 12.5px; color: var(--muted); margin: 4px 0 0; line-height: 1.55; }

.opt-table { overflow-x: auto; }
.opt-table table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.opt-table th,
.opt-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
}
.opt-table th { color: var(--muted); font-weight: 600; }
.opt-table code {
  background: var(--bg);
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--font-mono);
}
.opt-table .suggested { color: #10b981; font-weight: 700; }

.config-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 0;
  border-bottom: 1px solid var(--line);
}
.config-label {
  width: 90px;
  flex: none;
  font-size: 12.5px;
  color: var(--muted);
}
.config-value { font-size: 13.5px; }
.config-actions { display: flex; gap: 8px; margin-top: 14px; }
.health-box {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
}
.health-box.ok { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.health-box.fail { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.cfg-edit {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}
.cfg-edit .config-row { border-bottom: none; padding: 5px 0; }
.cfg-edit .input { flex: 1; }
.cfg-msg { margin-left: 10px; font-size: 12.5px; color: var(--accent); }

/* ───── 聊天 ───── */
.chat-section {
  flex: 1;
  min-height: 0;
  gap: 10px;
}
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.chat-head-left { display: flex; align-items: center; gap: 10px; }
.chat-head-left h2 { font-size: 15px; margin: 0; font-weight: 700; }
.chat-head-right { display: flex; align-items: center; gap: 8px; }
.session-input { width: 120px; font-size: 12.5px; }

/* 聊天窗口：撑满剩余视口，而非固定 480px */
.chat-window {
  flex: 1;
  min-height: 260px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 空状态 */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--muted);
  padding: 24px;
  gap: 6px;
}
.chat-empty-icon { opacity: 0.45; margin-bottom: 6px; }
.chat-empty-title { font-size: 14.5px; font-weight: 600; color: var(--text-secondary); margin: 0; }
.chat-empty-hint { font-size: 12.5px; margin: 0; line-height: 1.7; }
.chat-tip { display: block; margin-top: 10px; font-size: 11.5px; opacity: 0.75; }

/* 消息 */
.chat-msg { display: flex; gap: 10px; align-items: flex-start; }
.chat-msg.user { flex-direction: row-reverse; }
.chat-avatar {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  border: 1px solid var(--line);
  color: var(--muted);
}
.chat-avatar.assistant {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.chat-bubble {
  max-width: 75%;
  padding: 9px 13px;
  border-radius: 12px;
  font-size: 13.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat-bubble.md { white-space: normal; }
.chat-msg.user .chat-bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.chat-msg.assistant .chat-bubble {
  background: var(--bg);
  border: 1px solid var(--line);
  border-bottom-left-radius: 4px;
}

/* markdown 渲染样式（assistant 消息） */
.md-body :deep(p) { margin: 0 0 8px; }
.md-body :deep(p:last-child) { margin-bottom: 0; }
.md-body :deep(ul),
.md-body :deep(ol) { margin: 4px 0; padding-left: 18px; }
.md-body :deep(li) { margin-bottom: 3px; }
.md-body :deep(code) {
  background: var(--card);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--font-mono);
}
.md-body :deep(pre) {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 6px 0;
}
.md-body :deep(pre code) { background: none; padding: 0; font-size: 12px; }
.md-body :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 12.5px; }
.md-body :deep(th),
.md-body :deep(td) { border: 1px solid var(--line); padding: 5px 8px; text-align: left; }
.md-body :deep(th) { background: var(--card); }
.md-body :deep(blockquote) {
  margin: 6px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--accent);
  color: var(--muted);
}
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) { margin: 8px 0 4px; font-size: 14px; }
.md-body :deep(a) { color: var(--accent); }
.md-body :deep(hr) { border: none; border-top: 1px solid var(--line); margin: 10px 0; }

/* 流式输出光标 */
.stream-cursor {
  display: inline-block;
  width: 7px;
  height: 1em;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  border-radius: 1px;
  animation: cursor-blink 1s step-end infinite;
}
@keyframes cursor-blink { 50% { opacity: 0; } }

.chat-input-row { display: flex; gap: 8px; flex: none; }
.chat-input {
  flex: 1;
  resize: none;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  color: var(--text);
  font-size: 13.5px;
  font-family: inherit;
}
.chat-input:focus { outline: none; border-color: var(--accent); }
.send-btn { align-self: flex-end; }
</style>
